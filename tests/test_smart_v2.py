"""Controlled synthetic tests for Smart v2; no held-out inputs are read."""
import pytest

from app.strategy.models import StrategyPolicy
from app.strategy.smart_v2 import commitment_penalty, sla_risk_penalty
from tests.mvp2_support import config, offer, selected
from tests.test_mvp3 import run3


def v2_policy(**changes):
    return StrategyPolicy.model_validate({
        **StrategyPolicy().model_dump(),
        "base_reservation_wage": 60,
        "min_reservation_wage": 60,
        "max_reservation_wage": 60,
        "opportunity_fraction": 0,
        "use_reposition": False,
        "use_cancellation": False,
        "use_smart_v2_scoring": True,
        **changes,
    })


@pytest.mark.parametrize("minutes,expected", [(20, 0), (30, 10), (60, 70)])
def test_commitment_penalty_is_progressive(minutes, expected):
    assert commitment_penalty(minutes, 25, 2) == expected


@pytest.mark.parametrize("margin,expected", [(20, 0), (8, 4), (1, 18)])
def test_sla_risk_penalty_increases_as_margin_shrinks(margin, expected):
    assert sla_risk_penalty(margin, 10, 2) == expected


def test_negative_sla_margin_is_infeasible():
    assert sla_risk_penalty(-1, 10, 2) == float("inf")


def test_idle_short_value_long_mediocre_and_long_high_value():
    cfg = config(hours=3)
    cases = (
        offer(cfg, order_id="SHORT", estimated_pickup_min=5,
              restaurant_prep_min=5, estimated_delivery_min=10, base_pay_mxn=80,
              est_tip_mxn=0),
        offer(cfg, at=70, order_id="LONG_MEDIOCRE", estimated_pickup_min=10,
              restaurant_prep_min=15, estimated_delivery_min=30, base_pay_mxn=80,
              est_tip_mxn=0),
        offer(cfg, at=115, order_id="LONG_HIGH", estimated_pickup_min=10,
              restaurant_prep_min=15, estimated_delivery_min=30, base_pay_mxn=200,
              est_tip_mxn=0),
    )
    result, _ = run3(cfg, *cases, settings=v2_policy())
    decisions = {row["order_id"]: row for row in selected(result, "decision")}
    assert decisions["SHORT"]["decision"] == "ACCEPT"
    assert decisions["LONG_MEDIOCRE"]["decision"] == "SKIP"
    assert decisions["LONG_MEDIOCRE"]["smart_v2"]["decision_cause"] == "commitment_penalty"
    assert decisions["LONG_HIGH"]["decision"] == "ACCEPT"
    assert all(row["binding_constraint"] is None for row in decisions.values())


def test_batching_uses_small_increment_and_rejects_large_low_value_increment():
    cfg = config(hours=2)
    events = (
        offer(cfg, order_id="ACTIVE", estimated_pickup_min=5,
              restaurant_prep_min=5, estimated_delivery_min=20, base_pay_mxn=100),
        offer(cfg, at=1, order_id="SMALL_BATCH", distance_pickup_km=.2,
              distance_delivery_km=.3, estimated_pickup_min=2,
              restaurant_prep_min=0, estimated_delivery_min=3, base_pay_mxn=35,
              est_tip_mxn=0),
        offer(cfg, at=2, order_id="LARGE_BATCH", distance_pickup_km=2,
              distance_delivery_km=3, estimated_pickup_min=10,
              restaurant_prep_min=5, estimated_delivery_min=10, base_pay_mxn=15,
              est_tip_mxn=0),
    )
    result, _ = run3(cfg, *events, settings=v2_policy(sla_time_multiplier=3,
                                                       sla_buffer_min=30))
    decisions = {row["order_id"]: row for row in selected(result, "decision")}
    small = decisions["SMALL_BATCH"]["smart_v2"]
    large = decisions["LARGE_BATCH"]["smart_v2"]
    assert decisions["SMALL_BATCH"]["decision"] == "ACCEPT"
    assert small["mode"] == "batching" and small["incremental_time_min"] == pytest.approx(5)
    assert small["service_time_min"] == pytest.approx(5)
    assert decisions["LARGE_BATCH"]["decision"] == "SKIP"
    assert large["decision_cause"] == "batch_incremental_value"


def test_sla_infeasible_has_precise_internal_cause_and_no_false_wage_binding():
    cfg = config()
    events = (
        offer(cfg, order_id="A", estimated_pickup_min=5,
              estimated_delivery_min=20),
        offer(cfg, at=2, order_id="B", estimated_pickup_min=20,
              restaurant_prep_min=20, estimated_delivery_min=20),
    )
    result, _ = run3(cfg, *events,
                     settings=v2_policy(sla_time_multiplier=1, sla_buffer_min=0))
    rejected = selected(result, "decision")[1]
    assert rejected["decision"] == "SKIP"
    assert rejected["binding_constraint"] is None
    assert rejected["smart_v2"]["decision_cause"] == "sla_infeasible"
    assert "SLA" in rejected["reason"]


def test_rejecting_long_idle_order_preserves_availability_for_better_followup():
    cfg = config(hours=2)
    long_order = offer(cfg, order_id="LOCK_IN", estimated_pickup_min=10,
                       restaurant_prep_min=15, estimated_delivery_min=30,
                       base_pay_mxn=80, est_tip_mxn=0)
    better = offer(cfg, at=1, order_id="BETTER", estimated_pickup_min=2,
                   restaurant_prep_min=1, estimated_delivery_min=5,
                   base_pay_mxn=90, est_tip_mxn=0)
    improved, _ = run3(cfg, long_order, better, settings=v2_policy())
    current, _ = run3(cfg, long_order, better,
                      settings=v2_policy(use_smart_v2_scoring=False))
    improved_decisions = selected(improved, "decision")
    current_decisions = selected(current, "decision")
    assert [row["decision"] for row in improved_decisions] == ["SKIP", "ACCEPT"]
    assert current_decisions[0]["decision"] == "ACCEPT"
    assert improved_decisions[1]["smart_v2"]["mode"] == "idle"


def test_hard_constraint_still_dominates_absurd_pay():
    cfg = config()
    result, _ = run3(cfg, offer(cfg, weight_kg=999, base_pay_mxn=1_000_000),
                     settings=v2_policy())
    decision = selected(result, "decision")[0]
    assert decision["decision"] == "SKIP"
    assert decision["binding_constraint"] == "vehicle_capacity"
    assert result.metrics.safety_violations == 0
