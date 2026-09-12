from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from app.decision.engine import DecisionService
from app.logging.decision_log import DecisionLog
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.services.strategy_store import StrategyStore


def semantic(response):
    return response.model_dump(exclude={"latency_ms"})


def test_repeated_inputs(evaluate):
    expected = semantic(evaluate())
    for _ in range(100):
        assert semantic(evaluate()) == expected


def test_snapshot_is_deeply_immutable(snapshot):
    with pytest.raises(TypeError):
        snapshot.zone_values[7] = 0
    with pytest.raises(TypeError):
        snapshot.vehicle_profiles["moto"] = snapshot.vehicle_profiles["bike"]
    with pytest.raises(ValidationError):
        snapshot.vehicle_profiles["moto"].max_weight_kg = 1000


def test_strategy_replacement_stale_and_log_lookup(client, payload, monkeypatch):
    original = client.post("/decide", json=payload).json()
    service = client.app.state.decisions
    service.strategies.replace(StrategySnapshot(version="v2", is_stale=True, reservation_wage_mxn_hr=10000))
    updated = client.post("/decide", json={**payload, "order_id": "NEXT"}).json()
    assert updated["decision"] == "SKIP" and updated["degraded"] is True
    monkeypatch.setattr(service.engine, "evaluate", lambda *args: pytest.fail("Lookup re-evaluated decision"))
    stored = client.get("/decisions/TEST-001").json()
    assert stored["decision"] == original["decision"]
    assert stored["reason"] == original["reason"]
    assert stored["strategy_snapshot"]["version"] == "mvp1-v1"


def test_parallel_replays_and_log_integrity(payload, snapshot):
    service = DecisionService(StrategyStore(snapshot), DecisionLog())
    order = DecideRequest.model_validate(payload)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: service.decide(order), range(100)))
    assert all(semantic(result) == semantic(results[0]) for result in results)
    assert len(service.log.history(order.order_id)) == 100
    retrieved = service.log.get(order.order_id)
    retrieved.inputs.clear()
    assert service.log.get(order.order_id).inputs


def test_default_state_not_advanced_by_other_requests(client, payload):
    first = client.post("/decide", json=payload).json()
    client.post("/decide", json={**payload, "courier_state_overrides": {"continuous_riding_min": 240}})
    repeat = client.post("/decide", json=payload).json()
    assert {k: v for k, v in first.items() if k != "latency_ms"} == {k: v for k, v in repeat.items() if k != "latency_ms"}


def test_snapshot_requires_all_vehicles(snapshot):
    with pytest.raises(ValidationError):
        StrategySnapshot(vehicle_profiles={"moto": snapshot.vehicle_profiles["moto"]})


def test_decision_path_does_not_require_network_or_files(payload, snapshot, monkeypatch):
    service = DecisionService(StrategyStore(snapshot), DecisionLog())
    order = DecideRequest.model_validate(payload)
    def forbidden(*args, **kwargs):
        pytest.fail("Fast path attempted external I/O")
    monkeypatch.setattr("socket.socket", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr("io.open", forbidden)
    assert service.decide(order).decision == "ACCEPT"
