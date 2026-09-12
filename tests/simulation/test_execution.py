from copy import deepcopy
from datetime import timedelta

import pytest

from app.agents.baseline import GreedyRateBaseline
from app.agents.smart import SmartAgent
from app.models.strategy import StrategySnapshot
from app.simulation.simulator import Simulator
from tests.mvp2_support import config, offer, run, selected, stream


def test_accept_then_execution_then_payment():
    cfg = config()
    result = run(cfg, offer(cfg))
    decision = selected(result, "decision")[0]
    assert decision["decision"] == "ACCEPT"
    assert decision["courier_state"]["gross_earnings"] == 0
    assert any(e.get("current_weight_kg") == 1 for e in selected(result, "position_update"))
    completion = next(e for e in selected(result, "earnings_update") if "completed_order_id" in e)
    assert completion["sim_time"] == (cfg.simulation.simulation_start_time + timedelta(minutes=10)).isoformat()
    assert completion["gross_earnings_mxn"] == 1010
    assert result.metrics.operating_costs_mxn == pytest.approx(3.6)
    assert result.metrics.orders_completed == 1
    assert not result.state.in_flight_orders
    assert result.state.current_sim_time == cfg.shift_end
    assert result.metrics.idle_time_min == 50
    assert result.metrics.late_deliveries == 0


def test_skip_never_adds_load_or_earnings():
    cfg = config()
    result = run(cfg, offer(cfg, base_pay_mxn=0, est_tip_mxn=0))
    assert result.metrics.orders_skipped == 1
    assert result.metrics.orders_accepted == result.metrics.orders_completed == 0
    assert result.metrics.net_earnings_mxn == result.metrics.distance_traveled_km == 0
    assert result.metrics.idle_time_min == 60
    assert all(e["current_weight_kg"] == 0 for e in selected(result, "position_update"))


def test_stacking_serial_execution_and_remaining_overrides():
    cfg = config()
    result = run(cfg, offer(cfg), offer(cfg, at=2, order_id="TWO"))
    second = selected(result, "decision")[1]
    pending = second["decision_request"]["courier_state_overrides"]["in_flight_orders"]
    assert pending[0]["estimated_pickup_min"] == 3
    assert pending[0]["estimated_delivery_min"] == 5
    assert second["decision_request"]["courier_state_overrides"]["continuous_riding_min"] == 2
    assert any(e["current_weight_kg"] == 2 for e in selected(result, "position_update"))
    completed = [e for e in selected(result, "earnings_update") if "completed_order_id" in e]
    assert [e["completed_order_id"] for e in completed] == ["ONE", "TWO"]
    assert completed[-1]["sim_time"] == (cfg.simulation.simulation_start_time + timedelta(minutes=20)).isoformat()
    assert result.metrics.gross_earnings_mxn == 2020
    assert result.metrics.operating_costs_mxn == pytest.approx(7.2)


def test_two_agents_own_all_mutable_state():
    cfg = config()
    source = stream(cfg, offer(cfg))
    original = deepcopy(source)
    first = Simulator(cfg, SmartAgent()).run(source)
    second = Simulator(cfg, GreedyRateBaseline()).run(source)
    first.state.in_flight_orders.clear()
    first.state.gross_earnings = -100
    first.log.events.clear()
    assert second.state.gross_earnings == 1010
    assert second.log.events
    assert source == original


@pytest.mark.parametrize("vehicle", ["moto", "car", "bike"])
def test_capacity_in_execution(vehicle):
    cfg = config(vehicle=vehicle)
    capacity = StrategySnapshot().vehicle_profiles[vehicle].max_weight_kg
    result = run(cfg, offer(cfg, weight_kg=capacity), offer(cfg, at=1, order_id="OVER", weight_kg=.1))
    assert selected(result, "decision")[1]["binding_constraint"] == "vehicle_capacity"
    assert result.metrics.safety_violations == 0


def test_mandatory_break_is_real_twenty_minute_interval():
    cfg = config(hours=6)
    result = run(cfg, offer(cfg, estimated_pickup_min=120, estimated_delivery_min=120),
                 offer(cfg, at=245, order_id="DURING"), offer(cfg, at=260, order_id="AFTER"))
    decisions = selected(result, "decision")
    assert decisions[0]["decision"] == "ACCEPT"
    assert decisions[1]["binding_constraint"] == "mandatory_break"
    assert decisions[2]["decision"] == "ACCEPT"
    override = decisions[2]["decision_request"]["courier_state_overrides"]
    assert override["continuous_riding_min"] == 0
    assert override["last_break_end_time"] == "2026-03-21T22:20:00"
    assert result.metrics.safety_violations == 0


def test_heat_break_and_boundary():
    cfg = config(start="2026-03-21T12:00:00", hours=3)
    result = run(cfg, offer(cfg, estimated_pickup_min=45, estimated_delivery_min=45),
                 offer(cfg, at=95, order_id="DURING"), offer(cfg, at=110, order_id="AFTER"))
    assert selected(result, "decision")[1]["binding_constraint"] == "mandatory_break"
    assert selected(result, "decision")[2]["decision_request"]["courier_state_overrides"]["continuous_riding_min"] == 0
    assert result.metrics.safety_violations == 0


def test_exact_shift_end_completion_precedes_shift_end_event():
    cfg = config(hours=1/6)
    result = run(cfg, offer(cfg))
    assert result.metrics.orders_completed == 1
    assert result.log.events[-1]["event"] == "shift_end"
    assert result.metrics.safety_violations == 0


def test_flagged_arrival_and_late_shift_refused():
    cfg = config(start="2026-03-21T21:55:00", hours=1/6)
    result = run(cfg, offer(cfg, zone_dropoff=11), offer(cfg, at=1, order_id="LATE"))
    assert [e["binding_constraint"] for e in selected(result, "decision")] == ["flagged_zone_night", "shift_end_infeasible"]


def test_reject_reuse_of_simulator():
    cfg = config()
    simulator = Simulator(cfg, SmartAgent())
    source = stream(cfg, offer(cfg))
    simulator.run(source)
    with pytest.raises(ValueError, match="new simulator"):
        simulator.run(source)


def test_shift_start_metadata_must_match_experiment_config():
    cfg = config()
    source = stream(cfg, offer(cfg))
    source[0]["seed"] = 999
    with pytest.raises(ValueError, match="shift_start fields"):
        Simulator(cfg, SmartAgent()).run(source)


@pytest.mark.parametrize("change", ["duplicate", "wrong_vehicle", "after_end", "nonchronological"])
def test_invalid_stream_rejected(change):
    cfg = config()
    source = stream(cfg, offer(cfg), offer(cfg, at=1, order_id="TWO"))
    if change == "duplicate":
        source[2]["order_id"] = "ONE"
    elif change == "wrong_vehicle":
        source[1]["vehicle"] = "car"
    elif change == "after_end":
        source[2]["sim_time"] = (cfg.shift_end + timedelta(minutes=1)).isoformat()
    else:
        source[1], source[2] = source[2], source[1]
    with pytest.raises(ValueError):
        Simulator(cfg, SmartAgent()).run(source)
