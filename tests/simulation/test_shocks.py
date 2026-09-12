from datetime import timedelta

import pytest

from tests.mvp2_support import config, offer, run, selected, shock


def test_surge_zone_duration_and_locked_accepted_payment():
    cfg = config()
    result = run(cfg, shock(cfg, 0, "surge", zone=7, multiplier=2, duration_min=5),
                 offer(cfg), offer(cfg, at=1, order_id="OTHER", zone_pickup=8),
                 offer(cfg, at=5, order_id="EXPIRED"))
    offers = selected(result, "order_offered")
    assert [e["surge_multiplier"] for e in offers] == [2, 1, 1]
    # First order completes after expiry; the accepted price is not repriced.
    first = next(e for e in selected(result, "earnings_update") if e.get("completed_order_id") == "ONE")
    assert first["gross_earnings_mxn"] == 2010


def test_rain_reschedules_active_travel_and_expires():
    cfg = config(rain_travel_time_multiplier=2)
    result = run(cfg, offer(cfg), shock(cfg, 2, "rain", duration_min=4), offer(cfg, at=6, order_id="AFTER"))
    first = next(e for e in selected(result, "earnings_update") if e.get("completed_order_id") == "ONE")
    assert first["sim_time"] == "2026-03-21T18:12:00"
    assert first["late"] is True
    assert selected(result, "order_offered")[1]["estimated_pickup_min"] == 5
    assert result.metrics.operating_costs_mxn == pytest.approx(7.2)


def test_rain_affects_future_estimates_not_distances():
    cfg = config(rain_travel_time_multiplier=2)
    result = run(cfg, shock(cfg, 0, "rain", duration_min=30), offer(cfg))
    actual = selected(result, "order_offered")[0]
    assert actual["estimated_pickup_min"] == actual["estimated_delivery_min"] == 10
    assert actual["distance_pickup_km"] == 1
    assert result.metrics.orders_completed == 1
    assert result.metrics.late_deliveries == 0


def test_closure_penalty_active_and_future_zone_scoped_and_expiring():
    cfg = config(closure_delay_min=7)
    result = run(cfg, offer(cfg), shock(cfg, 2, "closure", zone=7, duration_min=5),
                 offer(cfg, at=3, order_id="MATCH"),
                 offer(cfg, at=4, order_id="OTHER", zone_pickup=8, zone_dropoff=8),
                 offer(cfg, at=7, order_id="EXPIRED"))
    assert [e["restaurant_prep_min"] for e in selected(result, "order_offered")] == [0, 7, 0, 0]
    first = next(e for e in selected(result, "earnings_update") if e.get("completed_order_id") == "ONE")
    assert first["sim_time"] == "2026-03-21T18:17:00" and first["late"]


def test_delay_recomputes_queued_work_and_updates_next_override():
    cfg = config()
    result = run(cfg, offer(cfg), offer(cfg, at=1, order_id="TWO"),
                 shock(cfg, 2, "delay", order_id="ONE", slip_min=5), offer(cfg, at=3, order_id="THREE"))
    pending = selected(result, "decision")[2]["decision_request"]["courier_state_overrides"]["in_flight_orders"]
    assert pending[0]["restaurant_prep_min"] == 5
    completions = [e for e in selected(result, "earnings_update") if "completed_order_id" in e]
    assert [e["sim_time"] for e in completions[:2]] == ["2026-03-21T18:15:00", "2026-03-21T18:25:00"]
    assert all(e["late"] for e in completions[:2])
    assert result.metrics.safety_violations == 0


def test_delay_for_unoffered_and_nonexistent_orders():
    cfg = config()
    result = run(cfg, shock(cfg, 0, "delay", order_id="ONE", slip_min=5),
                 shock(cfg, 0, "delay", order_id="NOT-OFFERED", slip_min=100), offer(cfg))
    assert selected(result, "order_offered")[0]["restaurant_prep_min"] == 5
    assert result.metrics.orders_completed == 1 and result.metrics.late_deliveries == 0


def test_road_only_closure_uses_explicit_conservative_global_penalty():
    cfg = config(closure_delay_min=4)
    result = run(cfg, shock(cfg, 0, "closure", road="SYNTHETIC-ROAD", duration_min=5), offer(cfg))
    assert selected(result, "order_offered")[0]["restaurant_prep_min"] == 4
    assert result.metrics.orders_completed == 1


def test_revised_completion_estimate_is_logged_after_delay():
    cfg = config()
    result = run(cfg, offer(cfg), shock(cfg, 2, "delay", order_id="ONE", slip_min=5))
    revised = [e for e in selected(result, "position_update")
               if e["sim_time"] == "2026-03-21T18:02:00" and e.get("action") == "state_updated"][0]
    assert revised["commitments"][0]["estimated_completion_time"] == "2026-03-21T18:15:00"
    assert revised["commitments"][0]["promised_completion_time"] == "2026-03-21T18:10:00"


def test_infeasible_after_shock_is_explicit_and_never_driven_after_shift_end():
    cfg = config(hours=0.25)
    result = run(cfg, offer(cfg), shock(cfg, 2, "delay", order_id="ONE", slip_min=20))
    assert result.metrics.orders_accepted == 1 and result.metrics.orders_completed == 0
    assert result.metrics.gross_earnings_mxn == 0
    assert result.metrics.operating_costs_mxn == pytest.approx(.4 * 1.2)
    assert result.metrics.uncompleted_orders == 1
    assert result.state.execution_hold == "shift_end_infeasible"
    assert any(e.get("action") == "post_accept_infeasible" for e in result.log.events)
    assert result.metrics.safety_violations == 0
    assert result.state.current_sim_time == cfg.shift_end


def test_rain_can_trigger_hold_then_recover_at_expiry():
    cfg = config(hours=1, rain_travel_time_multiplier=10)
    result = run(cfg, offer(cfg), shock(cfg, 2, "rain", duration_min=2))
    assert result.metrics.orders_completed == 1
    assert result.metrics.post_accept_infeasible == 1
    assert result.metrics.late_deliveries == 1
    assert any(e.get("action") == "execution_resumed" for e in result.log.events)


@pytest.mark.parametrize("start,fields,expected", [
    ("2026-03-21T21:45:00", {"zone_dropoff": 11}, "flagged_zone_night"),
    ("2026-03-21T12:00:00", {"estimated_pickup_min": 40, "estimated_delivery_min": 40}, "heat_rule"),
    ("2026-03-21T18:00:00", {"estimated_pickup_min": 110, "estimated_delivery_min": 110}, "mandatory_break"),
])
def test_shocks_do_not_turn_safe_acceptance_into_unsafe_execution(start, fields, expected):
    cfg = config(start=start, hours=6, rain_travel_time_multiplier=2)
    disruption = shock(cfg, 2, "delay", order_id="ONE", slip_min=30) if expected == "flagged_zone_night" else shock(cfg, 2, "rain", duration_min=300)
    result = run(cfg, offer(cfg, **fields), disruption)
    assert selected(result, "decision")[0]["decision"] == "ACCEPT"
    assert any(e.get("binding_constraint") == expected for e in selected(result, "position_update"))
    assert result.metrics.safety_violations == 0
