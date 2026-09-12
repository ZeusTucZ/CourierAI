from dataclasses import replace

import pytest

from app.agents.baseline import GreedyRateBaseline
from app.models.strategy import StrategySnapshot
from app.metrics.collector import collect_metrics
from app.metrics.comparison import compare, summarize
from tests.mvp2_support import config, offer, run


def test_accounting_can_be_rebuilt_only_from_event_log():
    cfg = config()
    result = run(cfg, offer(cfg), offer(cfg, at=1, order_id="TWO"))
    rebuilt = collect_metrics(result.log.events)
    assert rebuilt == result.metrics
    assert rebuilt.gross_earnings_mxn == 2020
    assert rebuilt.operating_costs_mxn == pytest.approx(7.2)
    assert rebuilt.net_earnings_mxn == pytest.approx(2012.8)
    assert rebuilt.orders_offered == rebuilt.orders_accepted == rebuilt.orders_completed == 2
    assert rebuilt.orders_skipped == rebuilt.safety_violations == rebuilt.late_deliveries == 0
    assert rebuilt.distance_traveled_km == pytest.approx(6)
    assert rebuilt.mxn_per_hour == pytest.approx(2012.8)
    assert rebuilt.mxn_per_km == pytest.approx(2012.8/6)
    assert rebuilt.mean_decision_latency_ms >= 0 and rebuilt.p95_decision_latency_ms >= 0


def test_zero_distance_and_zero_baseline_are_explicit():
    cfg = config()
    order = offer(cfg, base_pay_mxn=0, est_tip_mxn=0)
    baseline = run(cfg, order, agent=GreedyRateBaseline())
    smart = run(cfg, order)
    comparison = compare(baseline, smart)
    assert baseline.metrics.mxn_per_km is None
    assert comparison.improvement_pct is None
    assert comparison.net_earnings_difference_mxn == 0
    summary = summarize([comparison])
    assert summary["mean_improvement_pct"] is None
    assert summary["undefined_improvement_shifts"] == 1
    assert summary["smart_win_rate_pct"] == 0


@pytest.mark.parametrize("baseline_net,smart_net,percentage", [(100, 125, 25), (100, 75, -25), (-100, 0, -100)])
def test_comparison_formula(baseline_net, smart_net, percentage):
    cfg = config()
    order = offer(cfg)
    baseline = run(cfg, order, agent=GreedyRateBaseline())
    smart = run(cfg, order)
    baseline.metrics = replace(baseline.metrics, net_earnings_mxn=baseline_net)
    smart.metrics = replace(smart.metrics, net_earnings_mxn=smart_net)
    result = compare(baseline, smart)
    assert result.improvement_pct == percentage
    assert result.net_earnings_difference_mxn == smart_net - baseline_net
    assert result.orders_completed_difference == result.late_deliveries_difference == 0


def test_different_streams_cannot_be_compared():
    cfg = config()
    baseline = run(cfg, offer(cfg), agent=GreedyRateBaseline())
    smart = run(cfg, offer(cfg, base_pay_mxn=2000))
    with pytest.raises(ValueError, match="different event streams"):
        compare(baseline, smart)


def test_identical_stream_is_insufficient_if_physics_or_safety_differ():
    cfg = config()
    baseline = run(cfg, offer(cfg), agent=GreedyRateBaseline(StrategySnapshot(flagged_zones={8})))
    smart = run(cfg, offer(cfg))
    assert baseline.stream_sha256 == smart.stream_sha256
    with pytest.raises(ValueError, match="environment or safety"):
        compare(baseline, smart)


def test_missing_decision_cannot_silently_change_metrics():
    cfg = config()
    result = run(cfg, offer(cfg))
    with pytest.raises(ValueError, match="Every offer"):
        collect_metrics([event for event in result.log.events if event["event"] != "decision"])
