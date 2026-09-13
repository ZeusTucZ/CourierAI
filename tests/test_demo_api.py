"""Presentation session tests with controlled timelines; agents are not replaced in production."""
from copy import deepcopy
from datetime import datetime, timedelta
import asyncio
import pytest
from fastapi.testclient import TestClient

from app.demo.service import DemoService, DemoSession
from app.main import create_app


def timeline(seed, injections, source=None, shift_hours=4, vehicle="moto"):
    start = '2026-03-21T18:00:00'
    decision = {"event": "decision", "order_id": "ONE", "sim_time": start, "decision": "ACCEPT", "reason": "Recorded fixture reason.", "latency_ms": 1}
    frame = {"sim_time": start, "version": 0, "position": [-100.289,25.651], "zone": 7, "net_earnings": 100,
             "current_order": "ONE", "status": "to_dropoff", "routes": [{"edge_path": [[1,2,0],[2,3,0],[3,4,0]]}],
             "active_orders": [{"order_id": "ONE", "phase": "to_dropoff", "pickup": [-100.289,25.651],
                                "dropoff": [-100.3,25.66], "is_current": True}],
             "closures": {"type":"FeatureCollection","features":[]}}
    data = {"frames": [frame], "decisions": {"ONE":decision}, "offers": {"ONE":{}}, "detours": [], "metrics": {"net_earnings_mxn":100}}
    return {"seed":seed,"shift_hours":shift_hours,"vehicle":vehicle,"source":source or [{"event":"order_offered","order_id":"ONE","sim_time":start}],
            "start_time":start,"end_time":"2026-03-21T22:00:00","same_stream":True,"provenance":"test fixture",
            "start_position":[-100.289,25.651],"baseline_threshold":15,
            "orders":[{"order_id":"ONE","sim_time":start,"zone_pickup":7,"zone_dropoff":11}],
            "shocks":deepcopy(injections),"agents":{"baseline":deepcopy(data),"smart":deepcopy(data)}}


@pytest.fixture
def service():
    return DemoService(runner=timeline)


def test_live_api_start_socket_decision_pause_reset(service):
    with TestClient(create_app(demo_service=service)) as client:
        response=client.post('/demo/simulations',json={"seed":42, "shift_hours":2})
        assert response.status_code==202
        identifier=response.json()['id']
        with client.websocket_connect(f'/demo/simulations/{identifier}/ws') as socket:
            state=socket.receive_json()['state']
            if state['status']=='preparing':
                state=socket.receive_json()['state']
            assert state['same_stream'] is True
        assert state['shift_hours'] == 2
        assert state['vehicle'] == 'moto'
        assert state['orders'][0]['order_id']=='ONE'
        assert state['agents']['smart']['active_orders'][0]['order_id']=='ONE'
        details=client.get(f'/demo/simulations/{identifier}/decisions/ONE').json()
        assert details['smart']['reason']=='Recorded fixture reason.'
        assert client.post(f'/demo/simulations/{identifier}/control',json={"action":"pause"}).json()['status']=='paused'
        reset=client.post(f'/demo/simulations/{identifier}/control',json={"action":"reset"}).json()
        assert reset['orders']==[] and reset['agents']['smart']['net_earnings']==0
        assert client.get(f'/demo/simulations/{identifier}/decisions/ONE').status_code==404
        assert client.post(f'/demo/simulations/{identifier}/control',json={"action":"start"}).json()['orders']


def test_demo_vehicle_reaches_runner_and_state(service):
    with TestClient(create_app(demo_service=service)) as client:
        response = client.post('/demo/simulations', json={"seed": 42, "vehicle": "bike"})
        assert response.status_code == 202
        identifier = response.json()['id']
        with client.websocket_connect(f'/demo/simulations/{identifier}/ws') as socket:
            state = socket.receive_json()['state']
            if state['status'] == 'preparing':
                state = socket.receive_json()['state']
        assert state['vehicle'] == 'bike'


@pytest.mark.parametrize('kind',['rain','surge','closure','delay'])
def test_injected_shocks_are_shared_and_past_decisions_unchanged(service,kind):
    async def run():
        s=service.create(42)
        await s.task
        s.pause()
        before=deepcopy(s.data['agents']['smart']['decisions'])
        await service.inject(s.id,kind)
        await s.task
        assert s.error is None
        assert s.data['agents']['smart']['decisions']==before
        assert s.injections[0]['shock_type']==kind
        assert s.state()['shocks'][0]['shock_type']==kind
        assert s.status=='paused'
        await service.close()
    asyncio.run(run())


def test_clock_pause_speed_completion_and_reset(service):
    async def run():
        s=service.create(42)
        await s.task
        service.control(s.id,'speed',5)
        assert s.status=='running' and s.speed==5
        service.control(s.id,'pause')
        t=s.seconds()
        assert s.seconds()==t
        s.offset=14400
        assert s.state()['status']=='completed'
        assert s.state()['metrics']['smart']['net_earnings_mxn']==100
        service.control(s.id, 'reset')
        assert service.control(s.id, 'complete').state()['status']=='completed'
        service.control(s.id,'reset')
        assert s.state()['orders']==[]
        await service.close()
    asyncio.run(run())


def test_validation_unknown_session_and_invalid_speed(service):
    with TestClient(create_app(demo_service=service)) as client:
        assert client.get('/demo/simulations/missing').status_code==404
        assert client.post('/demo/simulations',json={"seed":-1}).status_code==422
        assert client.post('/demo/simulations/missing/control',json={"action":"speed","speed":100}).status_code==422


def test_failed_preparation_is_visible_and_not_fake_success():
    def broken(*args):
        raise FileNotFoundError('OSM graph missing')
    async def run():
        service=DemoService(runner=broken)
        s=service.create(1)
        await s.task
        assert s.state()['status']=='error' and 'OSM graph missing' in s.state()['error']
        await service.close()
    asyncio.run(run())


def test_new_demo_evicts_oldest_disconnected_session():
    async def run():
        service = DemoService(runner=timeline)
        sessions = []
        for seed in range(8):
            current = service.create(seed)
            await current.task
            sessions.append(current)
        sessions[0].subscribers = 1
        newest = service.create(8)
        await newest.task
        assert len(service.sessions) == 8
        assert sessions[0].id in service.sessions
        assert sessions[1].id not in service.sessions
        assert newest.id in service.sessions
        await service.close()
    asyncio.run(run())


def test_demo_explanation_is_grounded_cached_and_keeps_decision():
    from types import SimpleNamespace
    import json
    calls = []
    class FakeGemini:
        async def explain(self, payload):
            calls.append(json.loads(payload))
            return 'This order was skipped because completion would exceed the shift end by 100.89 minutes.'
    def constrained_timeline(seed, injections, source=None, shift_hours=4, vehicle="moto"):
        result = timeline(seed, injections, source, shift_hours, vehicle)
        smart = result['agents']['smart']['decisions']['ONE']
        smart.update(decision='SKIP', binding_constraint='shift_end_infeasible',
                     reason='Skipped: shift_end_infeasible; estimated completion is 100.89 minutes after shift end, including existing work.')
        return result
    advisor = SimpleNamespace(config=SimpleNamespace(enabled=True, api_key='fake'), client=FakeGemini())
    service = DemoService(runner=constrained_timeline)
    with TestClient(create_app(demo_service=service, advisor=advisor)) as client:
        identifier = client.post('/demo/simulations', json={'seed': 42}).json()['id']
        with client.websocket_connect(f'/demo/simulations/{identifier}/ws') as socket:
            state = socket.receive_json()['state']
            if state['status'] == 'preparing':
                state = socket.receive_json()['state']
        path = f'/demo/simulations/{identifier}/decisions/ONE/explanation'
        first = client.get(path)
        assert first.status_code == 200
        assert first.json()['source'] == 'gemini'
        assert '100.89' in first.json()['explanation']
        assert client.get(path).json() == first.json()
        assert len(calls) == 1
        assert set(calls[0]) == {'decision', 'structured_reason', 'binding_constraint', 'economics'}
        assert 'seed' not in str(calls[0]) and 'future' not in str(calls[0])
        assert client.get(f'/demo/simulations/{identifier}/decisions/ONE').json()['smart']['decision'] == 'SKIP'


def test_demo_explanation_fallback_when_gemini_fails():
    from types import SimpleNamespace
    class FailingGemini:
        async def explain(self, payload):
            raise TimeoutError()
    advisor = SimpleNamespace(config=SimpleNamespace(enabled=True, api_key='fake'), client=FailingGemini())
    service = DemoService(runner=timeline)
    with TestClient(create_app(demo_service=service, advisor=advisor)) as client:
        identifier = client.post('/demo/simulations', json={'seed': 42}).json()['id']
        with client.websocket_connect(f'/demo/simulations/{identifier}/ws') as socket:
            state = socket.receive_json()['state']
            if state['status'] == 'preparing':
                socket.receive_json()
        response = client.get(f'/demo/simulations/{identifier}/decisions/ONE/explanation')
        assert response.status_code == 200
        assert response.json()['source'] == 'fallback'
        assert response.json()['llm_explanation'] is None
        assert response.json()['explanation']
