"""Controlled end-to-end checks for the MVP 2 simulator."""
from dataclasses import replace
import pytest

from app.agents.baseline import GreedyRateBaseline
from app.agents.smart import SmartAgent
from app.logging.event_log import encode_events
from app.metrics.comparison import compare
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.simulation.config import ShiftConfig
from app.simulation.events import event_time
from app.simulation.generator import generate_shift
from app.simulation.replay import replay_shift
from app.simulation.simulator import Simulator
from app.simulation.shocks import WorldState, apply_shock
from app.simulation.events import Shock
from scripts.shift_common import run_pair
from tests.mvp2_support import make_order, make_shift, make_shock, make_state, run, selected, stream
from validate_format import check_event_log


def controlled_pair(cfg, *events, snapshot=None, threshold=None):
    source = stream(cfg, *events)
    snapshot = snapshot or StrategySnapshot()
    baseline = Simulator(cfg, GreedyRateBaseline(snapshot, threshold)).run(source)
    smart = Simulator(cfg, SmartAgent(snapshot)).run(source)
    return baseline, smart


def test_exact_requested_seed_and_distinct_seed_streams():
    cfg = ShiftConfig(seed=1234, shift_hours=8, vehicle="moto", start_location_zone=7)
    first, second = generate_shift(cfg), generate_shift(cfg)
    assert first == second
    assert encode_events(first) == encode_events(second)
    assert first != generate_shift(cfg.model_copy(update={"seed": 5678}))


def test_same_manual_world_independent_states_and_decisions():
    cfg = make_shift(start="2026-03-21T12:00:00")
    snapshot = StrategySnapshot(reservation_wage_mxn_hr=100, zone_values={7: -1000})
    orders = [
        make_order(cfg, at=0, order_id="ORD-001", zone_pickup=3, zone_dropoff=7,
                   distance_pickup_km=1, distance_delivery_km=4, base_pay_mxn=80, est_tip_mxn=0),
        make_order(cfg, at=8, order_id="ORD-002", zone_pickup=7, zone_dropoff=4,
                   distance_pickup_km=.5, distance_delivery_km=6, base_pay_mxn=120, est_tip_mxn=0),
        make_order(cfg, at=15, order_id="ORD-003", zone_pickup=3, zone_dropoff=9,
                   distance_pickup_km=2, distance_delivery_km=3, base_pay_mxn=65, est_tip_mxn=0),
    ]
    baseline, smart = controlled_pair(cfg, *orders, snapshot=snapshot)
    assert selected(baseline, "order_offered") == selected(smart, "order_offered")
    assert baseline.state is not smart.state
    b, s = selected(baseline, "decision"), selected(smart, "decision")
    assert (b[0]["decision"], s[0]["decision"]) == ("ACCEPT", "SKIP")
    assert b[1]["decision_request"]["courier_state_overrides"]["in_flight_orders"]
    assert s[1]["decision_request"]["courier_state_overrides"]["in_flight_orders"] == []
    assert b[1]["decision_request"]["order_id"] == s[1]["decision_request"]["order_id"]
    assert b[1]["courier_state"]["current_weight_kg"] == 1
    assert s[1]["courier_state"]["current_weight_kg"] == 0


def test_accept_commits_without_prepayment_then_completes_once():
    cfg = make_shift()
    result = run(cfg, make_order(cfg, weight_kg=2, volume_liters=8, est_tip_mxn=0))
    accepted = next(e for e in selected(result, "position_update") if e.get("action") == "state_updated" and e["commitments"])
    assert [job["order_id"] for job in accepted["commitments"]] == ["ONE"]
    assert accepted["current_weight_kg"] == 2 and accepted["current_volume_liters"] == 8
    assert not [e for e in selected(result, "earnings_update") if event_time(e) <= event_time(accepted)]
    completions = [e for e in selected(result, "earnings_update") if e.get("completed_order_id") == "ONE"]
    assert len(completions) == 1
    assert result.metrics.orders_completed == 1 and not result.state.in_flight_orders


def test_skip_only_increments_skip_count():
    cfg = make_shift()
    result = run(cfg, make_order(cfg, base_pay_mxn=0, est_tip_mxn=0))
    assert selected(result, "decision")[0]["decision"] == "SKIP"
    assert result.metrics.orders_skipped == 1
    assert result.state.current_weight_kg == result.state.current_volume_liters == 0
    assert not result.state.in_flight_orders
    assert result.metrics.gross_earnings_mxn == result.metrics.net_earnings_mxn == 0


def test_accepted_unfinished_order_has_no_gross_income():
    cfg = make_shift(hours=.25)
    result = run(cfg, make_order(cfg), make_shock(cfg, 2, "delay", order_id="ONE", slip_min=20))
    assert (result.metrics.orders_accepted, result.metrics.orders_completed) == (1, 0)
    assert result.metrics.gross_earnings_mxn == 0
    assert result.metrics.net_earnings_mxn <= 0


def test_batching_accepts_when_capacity_and_time_allow():
    cfg = make_shift()
    result = run(cfg, make_order(cfg, weight_kg=2, volume_liters=8),
                 make_order(cfg, at=1, order_id="B", weight_kg=1, volume_liters=5))
    assert [e["decision"] for e in selected(result, "decision")] == ["ACCEPT", "ACCEPT"]
    active = [e for e in selected(result, "position_update") if e.get("action") == "state_updated" and len(e["commitments"]) == 2]
    assert active and active[0]["current_weight_kg"] == 3 and active[0]["current_volume_liters"] == 13


@pytest.mark.parametrize("constraint,first,second", [
    ("vehicle_capacity", {"weight_kg": 12}, {"weight_kg": 4}),
    ("shift_end_infeasible", {}, {"estimated_delivery_min": 60}),
])
def test_second_order_safety_uses_pending_work(constraint, first, second):
    cfg = make_shift()
    result = run(cfg, make_order(cfg, **first),
                 make_order(cfg, at=1, order_id="B", base_pay_mxn=1_000_000, **second))
    decisions = selected(result, "decision")
    assert decisions[0]["decision"] == "ACCEPT"
    assert decisions[1]["decision"] == "SKIP"
    assert decisions[1]["binding_constraint"] == constraint
    assert decisions[1]["decision_request"]["courier_state_overrides"]["in_flight_orders"][0]["order_id"] == "ONE"


def test_surge_exact_expiry_and_zone_scope():
    cfg = make_shift()
    result = run(cfg, make_order(cfg, at=1, order_id="BEFORE"),
                 make_shock(cfg, 2, "surge", zone=7, multiplier=1.4, duration_min=30),
                 make_order(cfg, at=3, order_id="DURING"),
                 make_order(cfg, at=4, order_id="OTHER", zone_pickup=8),
                 make_order(cfg, at=31, order_id="LAST"),
                 make_order(cfg, at=32, order_id="EXPIRED"))
    assert [e["surge_multiplier"] for e in selected(result, "order_offered")] == [1, 1.4, 1, 1.4, 1]


def test_rain_changes_eta_economics_and_feasibility():
    cfg = make_shift(hours=.5, rain_travel_time_multiplier=1.25)
    order = make_order(cfg, estimated_pickup_min=10, estimated_delivery_min=10,
                       distance_pickup_km=1, distance_delivery_km=2)
    dry = run(cfg, order)
    wet = run(cfg, make_shock(cfg, 0, "rain", duration_min=25), order)
    offered = selected(wet, "order_offered")[0]
    assert offered["estimated_pickup_min"] == offered["estimated_delivery_min"] == 12.5
    assert selected(wet, "decision")[0]["economics"]["total_time_min"] > selected(dry, "decision")[0]["economics"]["total_time_min"]
    tight = make_shift(hours=.4, rain_travel_time_multiplier=1.25)
    assert selected(run(tight, make_shock(tight, 0, "rain", duration_min=25),
                        make_order(tight, estimated_pickup_min=10, estimated_delivery_min=10)), "decision")[0]["binding_constraint"] == "shift_end_infeasible"


def test_delay_and_closure_are_scoped_and_lateness_does_not_rewrite_accept():
    cfg = make_shift(closure_delay_min=12)
    result = run(cfg, make_order(cfg, order_id="A", zone_pickup=4, zone_dropoff=4),
                 make_order(cfg, at=1, order_id="B", zone_pickup=8, zone_dropoff=8),
                 make_shock(cfg, 2, "delay", order_id="A", slip_min=15),
                 make_shock(cfg, 3, "closure", zone=4, duration_min=20))
    decisions = selected(result, "decision")
    assert decisions[0]["decision"] == "ACCEPT"
    assert result.metrics.late_deliveries >= 1
    assert result.metrics.safety_violations == 0
    completions = {e["completed_order_id"]: e for e in selected(result, "earnings_update") if e.get("completed_order_id")}
    assert completions["A"]["late"] is True
    # B is delayed by A's serial queue, but the closure itself is zone-scoped.
    assert completions["B"]["sim_time"] > completions["A"]["sim_time"]


def test_delay_exact_eta_and_unrelated_future_order_unchanged():
    cfg = make_shift()
    result = run(cfg, make_order(cfg, order_id="A", estimated_pickup_min=10, estimated_delivery_min=15),
                 make_shock(cfg, 2, "delay", order_id="A", slip_min=15),
                 make_order(cfg, at=3, order_id="B", zone_pickup=8, zone_dropoff=8))
    before = next(e for e in selected(result, "position_update") if e.get("action") == "state_updated" and e["commitments"])
    after = next(e for e in selected(result, "position_update") if e["sim_time"].endswith("18:02:00") and e.get("action") == "state_updated")
    assert before["commitments"][0]["estimated_completion_time"].endswith("18:25:00")
    assert after["commitments"][0]["estimated_completion_time"].endswith("18:40:00")
    assert selected(result, "order_offered")[1]["restaurant_prep_min"] == 0


def test_closure_adds_twelve_minutes_only_to_affected_zone():
    cfg = make_shift(closure_delay_min=12)
    world = WorldState(cfg.simulation)
    affected = make_order(cfg, order_id="A", zone_pickup=4, zone_dropoff=4)
    other = make_order(cfg, order_id="B", zone_pickup=8, zone_dropoff=8)
    before = [world.prepare_offer(order, StrategySnapshot()) for order in (affected, other)]
    apply_shock(world, Shock.model_validate(make_shock(cfg, 0, "closure", zone=4, duration_min=20)))
    after = [world.prepare_offer(order, StrategySnapshot()) for order in (affected, other)]
    assert after[0].restaurant_prep_min == before[0].restaurant_prep_min + 12
    assert after[1].model_dump() == before[1].model_dump()


@pytest.mark.parametrize("constraint,changes,start,continuous", [
    ("shift_end_infeasible", {"estimated_delivery_min": 70}, "2026-03-21T18:00:00", 0),
    ("vehicle_capacity", {"weight_kg": 99}, "2026-03-21T18:00:00", 0),
    ("heat_rule", {}, "2026-03-21T12:00:00", 90),
    ("mandatory_break", {}, "2026-03-21T18:00:00", 240),
    ("flagged_zone_night", {"zone_dropoff": 11}, "2026-03-21T22:00:00", 0),
])
def test_absurd_pay_never_overrides_safety(constraint, changes, start, continuous):
    from app.simulation.state import to_us
    cfg = make_shift(start=start)
    state = make_state(cfg)
    state.continuous_riding_us = to_us(continuous)
    order = DecideRequest.model_validate(make_order(cfg, base_pay_mxn=1_000_000, **changes))
    for agent in (SmartAgent(), GreedyRateBaseline()):
        response = agent.decide(order, state)
        assert response.decision == "SKIP" and response.binding_constraint == constraint


@pytest.mark.parametrize("seed", range(1, 11))
def test_ten_seed_safety_and_fairness(seed):
    cfg = ShiftConfig(seed=seed, shift_hours=8, vehicle="moto", start_location_zone=7)
    baseline, smart, _ = run_pair(cfg)
    assert selected(baseline, "order_offered") == selected(smart, "order_offered"), f"seed={seed} world mismatch"
    for result in (baseline, smart):
        assert result.metrics.safety_violations == 0, f"seed={seed} agent={result.agent_name} log={result.log.events}"


def test_replay_decisions_and_official_event_validator(tmp_path):
    cfg = ShiftConfig(seed=1234, shift_hours=8, vehicle="moto", start_location_zone=7)
    baseline, smart, _ = run_pair(cfg)
    for result in (baseline, smart):
        path = tmp_path / f"{result.agent_name}-shift_1234.jsonl"
        result.log.write(path)
        assert not check_event_log(str(path))[0]
        assert [event_time(e) for e in result.log.events] == sorted(event_time(e) for e in result.log.events)
        assert replay_shift(path).decisions_checked == len(selected(result, "decision"))


def test_exact_earnings_and_no_double_counting():
    cfg = make_shift()
    snapshot = StrategySnapshot(reservation_wage_mxn_hr=0, zone_values={})
    result = run(cfg, make_order(cfg, order_id="A", base_pay_mxn=100, est_tip_mxn=0,
                                 distance_pickup_km=5, distance_delivery_km=5),
                 make_order(cfg, at=11, order_id="B", base_pay_mxn=70, est_tip_mxn=0,
                            distance_pickup_km=5, distance_delivery_km=10), agent=SmartAgent(snapshot))
    assert result.metrics.orders_completed == 2
    assert result.metrics.gross_earnings_mxn == 170
    assert result.metrics.operating_costs_mxn == pytest.approx(30)
    assert result.metrics.net_earnings_mxn == pytest.approx(140)
    assert len([e for e in selected(result, "earnings_update") if e.get("completed_order_id")]) == 2


@pytest.mark.parametrize("baseline_net,smart_net,expected", [(400, 500, 25), (500, 400, -20), (0, 10, None)])
def test_improvement_boundaries(baseline_net, smart_net, expected):
    cfg = make_shift()
    baseline, smart = controlled_pair(cfg, make_order(cfg))
    baseline.metrics = replace(baseline.metrics, net_earnings_mxn=baseline_net)
    smart.metrics = replace(smart.metrics, net_earnings_mxn=smart_net)
    assert compare(baseline, smart).improvement_pct == expected


def test_smart_loss_is_valid_and_reported_negative():
    cfg = make_shift()
    snapshot = StrategySnapshot(reservation_wage_mxn_hr=100, zone_values={7: -1000})
    baseline, smart = controlled_pair(cfg, make_order(cfg, base_pay_mxn=80, est_tip_mxn=0), snapshot=snapshot)
    comparison = compare(baseline, smart)
    assert smart.metrics.net_earnings_mxn < baseline.metrics.net_earnings_mxn
    assert comparison.improvement_pct < 0
    assert baseline.metrics.safety_violations == smart.metrics.safety_violations == 0


def test_dropoff_value_only_changes_smart_adjusted_rate():
    cfg = make_shift()
    snapshot = StrategySnapshot(reservation_wage_mxn_hr=6100, zone_values={7: 1000, 8: -1000})
    state = make_state(cfg)
    orders = [DecideRequest.model_validate(make_order(cfg, order_id=name, zone_dropoff=zone))
              for name, zone in (("HIGH", 7), ("LOW", 8))]
    smart = [SmartAgent(snapshot).decide(order, state) for order in orders]
    baseline = [GreedyRateBaseline(snapshot).decide(order, state) for order in orders]
    assert smart[0].economics.adjusted_rate_mxn_hr > smart[1].economics.adjusted_rate_mxn_hr
    assert (smart[0].decision, smart[1].decision) == ("ACCEPT", "SKIP")
    assert baseline[0].economics.adjusted_rate_mxn_hr == baseline[1].economics.adjusted_rate_mxn_hr


@pytest.mark.parametrize("offset,decision", [(0, "ACCEPT"), (-.001, "SKIP"), (.001, "ACCEPT")])
def test_smart_reservation_wage_boundary(offset, decision):
    cfg = make_shift()
    order = DecideRequest.model_validate(make_order(cfg))
    rate = SmartAgent().decide(order, make_state(cfg)).economics.adjusted_rate_mxn_hr
    response = SmartAgent(StrategySnapshot(reservation_wage_mxn_hr=rate - offset)).decide(order, make_state(cfg))
    assert response.decision == decision


def test_half_hour_shift_finishes_and_validates(tmp_path):
    cfg = make_shift(hours=.5)
    result = run(cfg, make_order(cfg), make_order(cfg, at=20, order_id="IMPOSSIBLE", estimated_delivery_min=20))
    assert result.log.events[-1]["event"] == "shift_end"
    assert selected(result, "decision")[-1]["binding_constraint"] == "shift_end_infeasible"
    assert result.metrics.orders_offered == 2 and result.metrics.safety_violations == 0
    path = tmp_path / "short.jsonl"
    result.log.write(path)
    assert not check_event_log(str(path))[0]
