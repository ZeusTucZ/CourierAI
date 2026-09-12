from dataclasses import asdict, dataclass
from statistics import mean

from app.metrics.results import ShiftResult


@dataclass(frozen=True)
class Comparison:
    seed: int
    baseline_net_mxn: float
    smart_net_mxn: float
    net_earnings_difference_mxn: float
    improvement_pct: float | None
    orders_completed_difference: int
    distance_difference_km: float
    late_deliveries_difference: int
    baseline_safety_violations: int
    smart_safety_violations: int

    def to_dict(self):
        return asdict(self)


def compare(baseline_result: ShiftResult, smart_result: ShiftResult) -> Comparison:
    if baseline_result.agent_name != "GreedyRateBaseline" or smart_result.agent_name != "SmartAgent":
        raise ValueError("Expected GreedyRateBaseline and SmartAgent")
    if baseline_result.stream_sha256 != smart_result.stream_sha256 or baseline_result.seed != smart_result.seed:
        raise ValueError("Cannot compare different event streams")
    baseline_meta, smart_meta = baseline_result.log.events[0], smart_result.log.events[0]
    if baseline_meta["simulation_config"] != smart_meta["simulation_config"] or any(
        baseline_meta["strategy_snapshot"][key] != smart_meta["strategy_snapshot"][key]
        for key in ("vehicle_profiles", "policy", "flagged_zones")
    ):
        raise ValueError("Cannot compare different environment or safety configurations")
    baseline, smart = baseline_result.metrics, smart_result.metrics
    difference = smart.net_earnings_mxn - baseline.net_earnings_mxn
    return Comparison(
        baseline_result.seed, baseline.net_earnings_mxn, smart.net_earnings_mxn, difference,
        difference / baseline.net_earnings_mxn * 100 if baseline.net_earnings_mxn else None,
        smart.orders_completed - baseline.orders_completed,
        smart.distance_traveled_km - baseline.distance_traveled_km,
        smart.late_deliveries - baseline.late_deliveries,
        baseline.safety_violations, smart.safety_violations,
    )


def summarize(comparisons: list[Comparison]) -> dict:
    if not comparisons:
        raise ValueError("At least one comparison required")
    percentages = [item.improvement_pct for item in comparisons if item.improvement_pct is not None]
    return {
        "shifts": len(comparisons),
        "mean_baseline_earnings_mxn": mean(item.baseline_net_mxn for item in comparisons),
        "mean_smart_earnings_mxn": mean(item.smart_net_mxn for item in comparisons),
        "mean_improvement_pct": mean(percentages) if percentages else None,
        "undefined_improvement_shifts": len(comparisons) - len(percentages),
        "smart_win_rate_pct": sum(item.net_earnings_difference_mxn > 0 for item in comparisons) / len(comparisons) * 100,
        "baseline_safety_violations": sum(item.baseline_safety_violations for item in comparisons),
        "smart_safety_violations": sum(item.smart_safety_violations for item in comparisons),
    }
