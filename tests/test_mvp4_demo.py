"""Tests for MVP 4 Demo simulation, APIs, state isolation, shocks, and safety scenarios."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.demo.session import DualSimulationSession
from app.demo.manager import SimulationManager


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_session_same_stream_and_independent_states():
    session = DualSimulationSession(seed=30004)
    # Stream SHA-256 is verified and identical
    assert session.sim_baseline.stream_digest == session.sim_smart.stream_digest
    assert session.stream_hash == session.sim_smart.stream_digest[:12]

    # Initial states are independent objects
    assert session.sim_baseline.state is not session.sim_smart.state
    assert session.sim_baseline.agent is not session.sim_smart.agent

    # Step through 5 events
    for _ in range(5):
        session.step()

    # Verify states remain independent
    assert session.sim_baseline.state.current_zone != 0
    assert session.sim_smart.state.current_zone != 0


def test_session_shock_injection_rain():
    session = DualSimulationSession(seed=30004)
    res = session.inject_shock("rain", duration_min=30)
    assert res["shock_type"] == "rain"
    assert session.sim_baseline.world.rain_factor == 1.25
    assert session.sim_smart.world.rain_factor == 1.25
    assert session.latest_shock is not None
    assert "RAIN" in session.latest_shock["message"]


def test_session_shock_injection_surge_closure_delay():
    session = DualSimulationSession(seed=30004)
    for _ in range(5):
        session.step()

    surge = session.inject_shock("surge", zone=3, multiplier=1.8, duration_min=45)
    assert surge["shock_type"] == "surge"

    closure = session.inject_shock("closure", zone=5, duration_min=20)
    assert closure["shock_type"] == "closure"

    delay = session.inject_shock("delay", slip_min=10)
    assert delay["shock_type"] == "delay"


def test_session_safety_scenarios():
    session = DualSimulationSession(seed=30004)
    for _ in range(3):
        session.step()

    # Vehicle capacity refusal
    cap = session.trigger_safety_scenario("vehicle_capacity")
    assert cap["baseline_decision"] == "SKIP"
    assert cap["smart_decision"] == "SKIP"
    assert cap["binding_constraint"] == "vehicle_capacity"

    # Shift end infeasible refusal
    end = session.trigger_safety_scenario("shift_end_infeasible")
    assert end["baseline_decision"] == "SKIP"
    assert end["smart_decision"] == "SKIP"
    assert end["binding_constraint"] == "shift_end_infeasible"


def test_api_simulation_lifecycle(client):
    # GET /simulation/state
    resp = client.get("/simulation/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "baseline" in data
    assert "smart" in data
    assert "comparison" in data

    # POST /simulation/start
    start_resp = client.post("/simulation/start", json={"seed": 30004, "playback_speed": 10})
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "running"

    # POST /simulation/pause
    pause_resp = client.post("/simulation/pause")
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    # POST /simulation/resume
    resume_resp = client.post("/simulation/resume")
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "running"

    # POST /simulation/speed
    speed_resp = client.post("/simulation/speed", json={"speed": 25})
    assert speed_resp.status_code == 200
    assert speed_resp.json()["playback_speed"] == 25

    # POST /simulation/reset
    reset_resp = client.post("/simulation/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "idle"


def test_api_shocks_and_scenarios(client):
    client.post("/simulation/start", json={"seed": 30004})

    shock_resp = client.post("/simulation/shock", json={"shock_type": "rain", "duration_min": 30})
    assert shock_resp.status_code == 200
    assert shock_resp.json()["shock_type"] == "rain"

    scenario_resp = client.post("/simulation/safety_scenario", json={"scenario_type": "vehicle_capacity"})
    assert scenario_resp.status_code == 200
    assert scenario_resp.json()["binding_constraint"] == "vehicle_capacity"


def test_api_inspector_and_historical(client):
    client.post("/simulation/start", json={"seed": 30004})

    # Trigger a decision to ensure an order exists in log
    client.post("/simulation/safety_scenario", json={"scenario_type": "vehicle_capacity"})

    events_resp = client.get("/simulation/events")
    assert events_resp.status_code == 200
    assert isinstance(events_resp.json(), list)

    order_id = next(e["order_id"] for e in reversed(events_resp.json()) if "order_id" in e)
    dec_resp = client.get(f"/simulation/decisions/{order_id}")
    assert dec_resp.status_code == 200
    dec_data = dec_resp.json()
    assert dec_data["order_id"] == order_id
    assert "smart" in dec_data
    assert "baseline" in dec_data

    # Historical evaluation endpoint
    hist_resp = client.get("/simulation/historical")
    assert hist_resp.status_code == 200
    assert hist_resp.json()["aggregate_economics"]["smart_win_rate_pct"] == 85.0
