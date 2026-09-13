import pytest

from app.decision.engine import DecisionEngine
from app.models.requests import DecideRequest


def inflight(**changes):
    return {"order_id": "ACTIVE", "weight_kg": 1, "volume_liters": 2,
            "estimated_pickup_min": 0, "estimated_delivery_min": 15, **changes}


def test_shift_elapsed_changes_default_end(evaluate):
    result = evaluate({"courier_state_overrides": {"shift_elapsed_hours": 7.9,
                                                  "continuous_riding_min": 0}})
    assert result.binding_constraint == "shift_end_infeasible"


def test_explicit_shift_end_has_precedence(evaluate):
    assert evaluate({"courier_state_overrides": {"shift_elapsed_hours": 7.9,
        "continuous_riding_min": 0, "shift_end_time": "2026-03-21T19:00:00"}}).decision == "ACCEPT"


def test_elapsed_without_riding_is_conservative(evaluate):
    assert evaluate({"courier_state_overrides": {"shift_elapsed_hours": 4}}).binding_constraint == "mandatory_break"


@pytest.mark.parametrize("end,binding", [("18:01:00", "mandatory_break"), ("18:00:00", None), ("17:59:00", None)])
def test_break_completion_boundary(evaluate, end, binding):
    assert evaluate({"courier_state_overrides": {
        "last_break_end_time": f"2026-03-21T{end}", "shift_elapsed_hours": 4}}).binding_constraint == binding


@pytest.mark.parametrize("time,binding", [("18:00:00", "mandatory_break"),
    ("18:19:59", "mandatory_break"), ("18:20:00", None)])
def test_twenty_minute_break_in_progress(evaluate, time, binding):
    # State provider schedules a 20-minute break from 18:00 until 18:20.
    assert evaluate({"sim_time": f"2026-03-21T{time}", "courier_state_overrides": {
        "continuous_riding_min": 0, "last_break_end_time": "2026-03-21T18:20:00",
        "shift_elapsed_hours": 4}}).binding_constraint == binding


def test_explicit_continuous_time_is_not_reset_by_old_break(evaluate):
    assert evaluate({"courier_state_overrides": {"last_break_end_time": "2026-03-21T17:59:00",
        "continuous_riding_min": 240}}).binding_constraint == "mandatory_break"


@pytest.mark.parametrize("dimension", ["weight_kg", "volume_liters"])
def test_inflight_load(evaluate, snapshot, dimension):
    profile = snapshot.vehicle_profiles["moto"]
    item = inflight(**{dimension: getattr(profile, f"max_{dimension}")})
    assert evaluate({"courier_state_overrides": {"in_flight_orders": [item]}}).binding_constraint == "vehicle_capacity"


def test_multiple_inflight_orders_are_summed(evaluate):
    result = evaluate({"courier_state_overrides": {"in_flight_orders": [inflight(weight_kg=11), inflight(weight_kg=11)]}})
    assert result.binding_constraint == "vehicle_capacity"


def test_inflight_time_blocks_shift_completion(evaluate):
    assert evaluate({"courier_state_overrides": {"in_flight_orders": [inflight()],
        "shift_end_time": "2026-03-21T18:20:00"}}).binding_constraint == "shift_end_infeasible"


def test_inflight_time_exact_boundary(evaluate):
    result = evaluate({"courier_state_overrides": {"in_flight_orders": [inflight()],
        "shift_end_time": "2026-03-21T18:25:00"}})
    assert result.decision == "ACCEPT"
    assert result.economics.total_time_min == 25


def test_inflight_includes_riding_commitment(evaluate):
    assert evaluate({"courier_state_overrides": {"in_flight_orders": [inflight()],
        "continuous_riding_min": 220}}).binding_constraint == "mandatory_break"


@pytest.mark.parametrize("time,riding,binding", [("12:00:00", 70, "heat_rule"),
    ("21:40:00", 0, "flagged_zone_night")])
def test_inflight_changes_heat_and_dropoff_feasibility(evaluate, time, riding, binding):
    assert evaluate({"sim_time": f"2026-03-21T{time}", "zone_dropoff": 11,
        "courier_state_overrides": {"in_flight_orders": [inflight()],
                                    "continuous_riding_min": riding}}).binding_constraint == binding


def test_incomplete_inflight_not_ignored(evaluate):
    result = evaluate({"courier_state_overrides": {"in_flight_orders": [{"order_id": "X"}]}})
    assert result.binding_constraint == "shift_end_infeasible"


def test_missing_inflight_load_not_ignored(evaluate):
    result = evaluate({"courier_state_overrides": {"in_flight_orders": [inflight(weight_kg=None)]}})
    assert result.binding_constraint == "vehicle_capacity"


def test_overrides_are_recorded(client, payload):
    payload["courier_state_overrides"].update(shift_elapsed_hours=3.7, in_flight_orders=[inflight()])
    body = client.post("/decide", json=payload).json()
    record = client.get("/decisions/TEST-001").json()
    assert record["inputs"]["courier_state"]["shift_elapsed_hours"] == 3.7
    assert record["inputs"]["courier_state"]["in_flight_orders"][0]["order_id"] == "ACTIVE"
    assert record["latency_ms"] == body["latency_ms"]


def test_offset_datetimes_use_supplied_local_hour(payload, snapshot):
    payload["sim_time"] = "2026-03-21T18:00:00-06:00"
    payload["courier_state_overrides"]["shift_end_time"] = "2026-03-22T00:10:00Z"
    assert DecisionEngine().evaluate(DecideRequest.model_validate(payload), snapshot).response.decision == "ACCEPT"
