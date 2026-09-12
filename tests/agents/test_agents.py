from datetime import timedelta

import pytest

from app.agents.baseline import GreedyRateBaseline
from app.agents.smart import SmartAgent
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.simulation.state import ActiveOrder, CourierState, to_us
from tests.mvp2_support import config, offer


@pytest.mark.parametrize("constraint,change,continuous", [
    ("flagged_zone_night", {"sim_time": "2026-03-21T22:00:00", "zone_dropoff": 11}, 0),
    ("mandatory_break", {}, 240),
    ("heat_rule", {"sim_time": "2026-03-21T12:00:00"}, 90),
    ("shift_end_infeasible", {"estimated_delivery_min": 70}, 0),
    ("vehicle_capacity", {"weight_kg": 99}, 0),
])
def test_both_agents_use_identical_hard_constraints(constraint, change, continuous):
    cfg = config(start=change.get("sim_time", "2026-03-21T18:00:00"))
    state = CourierState.for_shift(cfg)
    state.continuous_riding_us = to_us(continuous)
    order = DecideRequest.model_validate(offer(cfg, base_pay_mxn=1e9, **change))
    state.current_sim_time = order.sim_time
    for agent in (GreedyRateBaseline(), SmartAgent()):
        result = agent.decide(order, state)
        assert result.decision == "SKIP" and result.binding_constraint == constraint
        assert constraint in result.reason
        assert result.economics is None


@pytest.mark.parametrize("offset,decision", [(0, "ACCEPT"), (-.0001, "ACCEPT"), (.0001, "SKIP")])
def test_baseline_threshold_tie(offset, decision):
    cfg = config()
    order = DecideRequest.model_validate(offer(cfg))
    state = CourierState.for_shift(cfg)
    rate = GreedyRateBaseline().decide(order, state).economics.raw_rate_mxn_hr
    result = GreedyRateBaseline(threshold=rate + offset).decide(order, state)
    assert result.decision == decision
    assert result.binding_constraint == (None if decision == "ACCEPT" else "reservation_wage")


def test_baseline_ignores_zone_value():
    cfg = config()
    state = CourierState.for_shift(cfg)
    strategy = StrategySnapshot(reservation_wage_mxn_hr=6100, zone_values={7: 1000, 8: -1000})
    baseline = GreedyRateBaseline(strategy)
    smart = SmartAgent(strategy)
    first = DecideRequest.model_validate(offer(cfg, zone_dropoff=7))
    second = DecideRequest.model_validate(offer(cfg, zone_dropoff=8))
    assert baseline.decide(first, state).decision == baseline.decide(second, state).decision
    assert smart.decide(first, state).decision == "ACCEPT"
    assert smart.decide(second, state).decision == "SKIP"


def test_smart_reuses_engine_and_adapter_passes_real_state(monkeypatch):
    cfg = config()
    state = CourierState.for_shift(cfg)
    state.current_sim_time += timedelta(minutes=5)
    state.continuous_riding_us = to_us(5)
    order = DecideRequest.model_validate(offer(cfg, at=5))
    active = ActiveOrder.accepted(order, StrategySnapshot(), state.current_sim_time + timedelta(minutes=10))
    state.in_flight_orders.append(active)
    agent = SmartAgent()
    original = agent.service.engine.evaluate
    seen = []
    def capture(request, snapshot):
        seen.append(request)
        return original(request, snapshot)
    monkeypatch.setattr(agent.service.engine, "evaluate", capture)
    result = agent.decide(order.model_copy(update={"order_id": "NEW"}), state)
    assert len(seen) == 1
    overrides = seen[0].courier_state_overrides
    assert overrides.continuous_riding_min == 5
    assert overrides.shift_elapsed_hours == pytest.approx(5/60)
    assert overrides.shift_end_time == cfg.shift_end
    assert overrides.in_flight_orders[0].order_id == "ONE"
    assert agent.service.log.get("NEW").decision == result.decision
