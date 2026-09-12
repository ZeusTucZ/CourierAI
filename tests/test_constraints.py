import pytest


@pytest.mark.parametrize("time,delivery,binding", [
    ("21:40:00", 5, None), ("21:55:00", 5, "flagged_zone_night"),
    ("22:00:00", 0, "flagged_zone_night"), ("22:00:01", 5, "flagged_zone_night"),
])
def test_flagged_zone_boundary(evaluate, time, delivery, binding):
    response = evaluate({"sim_time": f"2026-03-21T{time}", "zone_dropoff": 11,
                         "estimated_delivery_min": delivery})
    assert response.binding_constraint == binding


@pytest.mark.parametrize("riding,binding", [(229.999, None), (230, None),
                                            (230.001, "mandatory_break"), (240, "mandatory_break")])
def test_mandatory_break_boundary(evaluate, riding, binding):
    assert evaluate({"courier_state_overrides": {"continuous_riding_min": riding}}).binding_constraint == binding


@pytest.mark.parametrize("time,riding,binding", [
    ("12:00:00", 80, None), ("12:00:00", 80.001, "heat_rule"),
    ("12:00:00", 90, "heat_rule"), ("16:00:00", 90, None),
    ("11:55:00", 85, "heat_rule"), ("15:55:00", 85, None),
    ("15:55:00", 86, "heat_rule"), ("11:40:00", 95, None),
])
def test_heat_boundary_and_crossings(evaluate, time, riding, binding):
    assert evaluate({"sim_time": f"2026-03-21T{time}",
                     "courier_state_overrides": {"continuous_riding_min": riding}}).binding_constraint == binding


@pytest.mark.parametrize("end,binding", [("18:10:00", None), ("18:09:59", "shift_end_infeasible"),
                                         ("18:10:01", None)])
def test_shift_end_boundary(evaluate, end, binding):
    response = evaluate({"courier_state_overrides": {"shift_end_time": f"2026-03-21T{end}"}})
    assert response.binding_constraint == binding


@pytest.mark.parametrize("vehicle", ["moto", "car", "bike"])
@pytest.mark.parametrize("dimension,limit", [("weight_kg", "max_weight_kg"), ("volume_liters", "max_volume_liters")])
def test_capacity_boundaries(evaluate, snapshot, vehicle, dimension, limit):
    value = getattr(snapshot.vehicle_profiles[vehicle], limit)
    assert evaluate({"vehicle": vehicle, dimension: value}).binding_constraint is None
    response = evaluate({"vehicle": vehicle, dimension: value + .001})
    assert response.binding_constraint == "vehicle_capacity"
    assert response.economics is None


@pytest.mark.parametrize("patch,binding", [
    ({"sim_time": "2026-03-21T22:00:00", "zone_dropoff": 11}, "flagged_zone_night"),
    ({"courier_state_overrides": {"continuous_riding_min": 240}}, "mandatory_break"),
    ({"sim_time": "2026-03-21T12:00:00", "courier_state_overrides": {"continuous_riding_min": 90}}, "heat_rule"),
    ({"courier_state_overrides": {"shift_end_time": "2026-03-21T18:05:00"}}, "shift_end_infeasible"),
    ({"weight_kg": 999}, "vehicle_capacity"),
])
def test_high_pay_never_overrides_safety(evaluate, monkeypatch, patch, binding):
    def forbidden(*args):
        pytest.fail("Economics ran before safety passed")
    monkeypatch.setattr("app.decision.engine.calculate_economics", forbidden)
    for pay in [0, 100, 1e12]:
        response = evaluate({**patch, "base_pay_mxn": pay})
        assert response.decision == "SKIP"
        assert response.binding_constraint == binding
        assert binding in response.reason
        assert 0 < len(response.reason.split()) < 40


def test_constraint_priority(evaluate):
    response = evaluate({"sim_time": "2026-03-21T22:00:00", "zone_dropoff": 11,
                         "weight_kg": 1000, "courier_state_overrides": {
                             "continuous_riding_min": 240, "shift_end_time": "2026-03-21T22:00:00"}})
    assert response.binding_constraint == "flagged_zone_night"


def test_prep_delay_affects_completion_not_riding(evaluate):
    result = evaluate({"restaurant_prep_min": 15, "courier_state_overrides": {
        "continuous_riding_min": 230, "shift_end_time": "2026-03-21T18:20:00"}})
    assert result.binding_constraint == "shift_end_infeasible"
