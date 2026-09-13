"""Speech can narrate visible route events without changing the simulation."""
import httpx
from fastapi.testclient import TestClient

from app.demo.service import DemoService, DemoSession
from app.main import create_app
from tests.test_demo_api import timeline


def test_route_speech_is_optional_and_only_uses_visible_events(monkeypatch):
    service = DemoService(runner=timeline)
    session = DemoSession(42)
    service.sessions[session.id] = session
    session.data = timeline(42, [], None)
    session.status = 'paused'
    event_time = session.data['start_time']
    session.data['shocks'] = [{'event': 'shock', 'shock_type': 'closure', 'sim_time': event_time}]
    session.data['agents']['smart']['detours'] = [
        {'sim_time': event_time, 'order_id': 'ONE', 'detour_distance_km': .17, 'detour_minutes': .4}]
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)
    path = f'/demo/speech/simulations/{session.id}/route-events/shock-0'
    with TestClient(create_app(demo_service=service)) as client:
        assert client.get('/demo/speech/status').json() == {'enabled': False}
        assert client.post(path).status_code == 503

        monkeypatch.setenv('ELEVENLABS_API_KEY', 'test-key')
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, content=b'fake-mp3')
        real_client = httpx.AsyncClient
        monkeypatch.setattr('app.demo.speech.httpx.AsyncClient',
                            lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
        assert client.get('/demo/speech/status').json() == {'enabled': True}
        assert client.post(path.replace('shock-0', 'shock-9')).status_code == 404
        result = client.post(path)
        assert result.status_code == 200 and result.content == b'fake-mp3'
        assert result.headers['content-type'] == 'audio/mpeg'
        assert requests[0].headers['xi-api-key'] == 'test-key'
        assert 'Smart route updated.' in requests[0].content.decode()
        assert 'Baseline' not in requests[0].content.decode()

        session.status = 'completed'
        assert client.post(path).status_code == 409
        assert len(requests) == 1
