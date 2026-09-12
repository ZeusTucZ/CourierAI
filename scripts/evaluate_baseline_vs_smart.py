"""Evaluation runner comparing FirstNearbyOrderBaseline against SmartAgent.
Strictly evaluation-only: no tuning, no parameter modifications, no data leakage.
"""
import csv
import json
import math
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from statistics import mean, median

from app.agents.nearby import FirstNearbyBaselineConfig, FirstNearbyOrderBaseline
from app.evaluation.freeze import load_frozen
from app.evaluation.runner import run_pair_v3
from app.simulation.config import ShiftConfig
from app.simulation.replay import logical

OUT = Path("artifacts")
OUT.mkdir(parents=True, exist_ok=True)

REPORTING_SEEDS = list(range(20001, 20021))
HARD_CONSTRAINTS = {
    "flagged_zone_night",
    "mandatory_break",
    "heat_rule",
    "shift_end_infeasible",
    "vehicle_capacity",
}


def quantile(values, p):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def run_evaluation():
    frozen_path = OUT / "final_strategy_config.json"
    frozen_sha = sha256(frozen_path.read_bytes()).hexdigest()
    profile, model, policy = load_frozen(frozen_path)
    baseline_cfg = FirstNearbyBaselineConfig.load()

    # Verify frozen profile & baseline provenance
    assert profile.name == "calibrated-b902d8308110"
    assert math.isclose(baseline_cfg.max_distance_km, 14.990869288322063, rel_tol=1e-6)
    assert baseline_cfg.profile_version == profile.name

    # Check seeds separation
    tuning_seeds = [int(line.strip()) for line in Path("evaluation/tuning_seeds.txt").read_text().splitlines() if line.strip() and not line.startswith("#")]
    heldout_old = [int(line.strip()) for line in Path("evaluation/heldout_seeds.txt").read_text().splitlines() if line.strip() and not line.startswith("#")]
    assert len(REPORTING_SEEDS) == 20
    assert not (set(REPORTING_SEEDS) & set(tuning_seeds)), "Overlap with tuning seeds!"
    assert not (set(REPORTING_SEEDS) & set(heldout_old)), "Overlap with previous held-out seeds!"

    results_table = []
    decision_diffs = []
    all_baseline_decisions = []
    baseline_distances_accepted = []
    baseline_skip_reasons = Counter()

    # Per-seed execution
    raw_results = {}
    for seed in REPORTING_SEEDS:
        cfg = ShiftConfig(
            seed=seed,
            shift_hours=8,
            vehicle="moto",
            start_location_zone=7,
            profile=profile,
        )
        # Execute paired shift
        baseline_res, smart_res = run_pair_v3(
            cfg, model, policy, output=None, baseline_config=baseline_cfg
        )

        # Enforce exact same order stream
        assert baseline_res.stream_sha256 == smart_res.stream_sha256, f"Stream mismatch on seed {seed}"
        assert baseline_res.metrics.safety_violations == 0, f"Baseline safety violation on seed {seed}"
        assert smart_res.metrics.safety_violations == 0, f"Smart safety violation on seed {seed}"

        raw_results[seed] = (baseline_res, smart_res)

        b_m = baseline_res.metrics
        s_m = smart_res.metrics

        diff = s_m.net_earnings_mxn - b_m.net_earnings_mxn
        improvement_pct = (diff / b_m.net_earnings_mxn * 100) if b_m.net_earnings_mxn != 0 else None

        if s_m.net_earnings_mxn > b_m.net_earnings_mxn:
            winner = "Smart"
        elif b_m.net_earnings_mxn > s_m.net_earnings_mxn:
            winner = "Baseline"
        else:
            winner = "Tie"

        results_table.append({
            "seed": seed,
            "baseline_net": round(b_m.net_earnings_mxn, 2),
            "smart_net": round(s_m.net_earnings_mxn, 2),
            "absolute_difference": round(diff, 2),
            "improvement_pct": round(improvement_pct, 2) if improvement_pct is not None else None,
            "winner": winner,
            "baseline_completed": b_m.orders_completed,
            "smart_completed": s_m.orders_completed,
            "baseline_distance": round(b_m.distance_traveled_km, 2),
            "smart_distance": round(s_m.distance_traveled_km, 2),
            "baseline_late": b_m.late_deliveries,
            "smart_late": s_m.late_deliveries,
            "baseline_safety": b_m.safety_violations,
            "smart_safety": s_m.safety_violations,
            "baseline_gross": round(b_m.gross_earnings_mxn, 2),
            "smart_gross": round(s_m.gross_earnings_mxn, 2),
            "baseline_costs": round(b_m.operating_costs_mxn, 2),
            "smart_costs": round(s_m.operating_costs_mxn, 2),
            "baseline_offered": b_m.orders_offered,
            "smart_offered": s_m.orders_offered,
            "baseline_accepted": b_m.orders_accepted,
            "smart_accepted": s_m.orders_accepted,
            "baseline_skipped": b_m.orders_skipped,
            "smart_skipped": s_m.orders_skipped,
            "baseline_idle_min": round(b_m.idle_time_min, 2),
            "smart_idle_min": round(s_m.idle_time_min, 2),
            "baseline_cancellations": b_m.orders_cancelled,
            "smart_cancellations": s_m.orders_cancelled,
            "baseline_mxn_per_hr": round(b_m.mxn_per_hour, 2),
            "smart_mxn_per_hr": round(s_m.mxn_per_hour, 2),
            "baseline_mxn_per_km": round(b_m.mxn_per_km, 2) if b_m.mxn_per_km is not None else None,
            "smart_mxn_per_km": round(s_m.mxn_per_km, 2) if s_m.mxn_per_km is not None else None,
            "smart_reposition_km": round(s_m.reposition_distance_km, 2),
        })

        # Compare decisions order by order
        b_decisions = {e["order_id"]: e for e in baseline_res.log.events if e["event"] == "decision"}
        s_decisions = {e["order_id"]: e for e in smart_res.log.events if e["event"] == "decision"}

        for order_id, b_event in b_decisions.items():
            s_event = s_decisions.get(order_id)
            if not s_event:
                continue

            b_dec = b_event["decision"]
            s_dec = s_event["decision"]

            b_req = b_event.get("decision_request", {})
            distance_total = b_req.get("distance_pickup_km", 0) + b_req.get("distance_delivery_km", 0)

            # Analyze baseline behavior
            if b_dec == "ACCEPT":
                category = "ACCEPT"
                baseline_distances_accepted.append(distance_total)
            elif b_event.get("binding_constraint") in HARD_CONSTRAINTS:
                category = b_event["binding_constraint"]
            elif b_event.get("reason", "").startswith("Skipped: total distance"):
                category = "distance"
            else:
                category = "simulator_feasibility_gate"

            baseline_skip_reasons[category] += 1
            all_baseline_decisions.append({
                "seed": seed,
                "order_id": order_id,
                "decision": b_dec,
                "category": category,
                "distance_km": distance_total,
            })

            # Check for disagreement
            if b_dec != s_dec:
                disagreement_type = f"Baseline {b_dec} / Smart {s_dec}"
                econ = s_event.get("economics") or {}
                # Historical signal from snapshot prediction if available
                strat_snap = s_event.get("strategy_snapshot", {})
                zone_preds = strat_snap.get("zone_predictions", {})
                pred_zone = zone_preds.get(str(b_req.get("zone_pickup"))) or zone_preds.get(b_req.get("zone_pickup"))

                diff_row = {
                    "seed": seed,
                    "order_id": order_id,
                    "baseline_decision": b_dec,
                    "smart_decision": s_dec,
                    "disagreement_category": disagreement_type,
                    "smart_reason": s_event.get("reason", ""),
                    "binding_constraint": s_event.get("binding_constraint"),
                    "distance_total_km": round(distance_total, 3),
                    "gross_pay_mxn": round(econ.get("gross_pay_mxn", 0), 2) if econ else None,
                    "operating_cost_mxn": round(econ.get("operating_cost_mxn", 0), 2) if econ else None,
                    "net_pay_mxn": round(econ.get("net_pay_mxn", 0), 2) if econ else None,
                    "raw_rate_mxn_hr": round(econ.get("raw_rate_mxn_hr", 0), 2) if econ else None,
                    "adjusted_rate_mxn_hr": round(econ.get("adjusted_rate_mxn_hr", 0), 2) if econ else None,
                    "reservation_wage_mxn_hr": round(econ.get("reservation_wage_mxn_hr", 0), 2) if econ else None,
                    "zone_value": round(econ.get("zone_value_mxn_hr", 0), 2) if econ and econ.get("zone_value_mxn_hr") is not None else None,
                    "opportunity_cost": round(econ.get("opportunity_cost_mxn", 0), 2) if econ and econ.get("opportunity_cost_mxn") is not None else None,
                    "historical_signal": str(pred_zone) if pred_zone else None,
                    "stacking_impact": econ.get("stacking_time_min"),
                }
                decision_diffs.append(diff_row)

    # Statistical Aggregations
    total_shifts = len(results_table)
    mean_baseline_net = mean(r["baseline_net"] for r in results_table)
    mean_smart_net = mean(r["smart_net"] for r in results_table)
    median_baseline_net = median(r["baseline_net"] for r in results_table)
    median_smart_net = median(r["smart_net"] for r in results_table)

    improvements = [r["improvement_pct"] for r in results_table if r["improvement_pct"] is not None]
    mean_improvement_pct = mean(improvements) if improvements else 0
    median_improvement_pct = median(improvements) if improvements else 0

    smart_wins = sum(1 for r in results_table if r["winner"] == "Smart")
    baseline_wins = sum(1 for r in results_table if r["winner"] == "Baseline")
    ties = sum(1 for r in results_table if r["winner"] == "Tie")

    smart_win_rate = smart_wins / total_shifts * 100
    baseline_win_rate = baseline_wins / total_shifts * 100
    tie_rate = ties / total_shifts * 100

    mean_baseline_completed = mean(r["baseline_completed"] for r in results_table)
    mean_smart_completed = mean(r["smart_completed"] for r in results_table)

    mean_baseline_distance = mean(r["baseline_distance"] for r in results_table)
    mean_smart_distance = mean(r["smart_distance"] for r in results_table)

    mean_baseline_late = mean(r["baseline_late"] for r in results_table)
    mean_smart_late = mean(r["smart_late"] for r in results_table)

    total_baseline_safety = sum(r["baseline_safety"] for r in results_table)
    total_smart_safety = sum(r["smart_safety"] for r in results_table)

    # Decision stats
    total_decisions = len(all_baseline_decisions)
    total_disagreements = len(decision_diffs)
    total_identical = total_decisions - total_disagreements
    pct_identical = (total_identical / total_decisions * 100) if total_decisions else 0
    pct_disagreement = (total_disagreements / total_decisions * 100) if total_decisions else 0

    disagreement_counts = Counter(d["disagreement_category"] for d in decision_diffs)
    b_acc_s_skip = disagreement_counts["Baseline ACCEPT / Smart SKIP"]
    b_skip_s_acc = disagreement_counts["Baseline SKIP / Smart ACCEPT"]

    # Baseline Behavior
    b_accepted_count = baseline_skip_reasons["ACCEPT"]
    b_accept_rate = (b_accepted_count / total_decisions * 100) if total_decisions else 0
    b_skip_rate = 100 - b_accept_rate
    b_skip_distance_pct = (baseline_skip_reasons["distance"] / total_decisions * 100) if total_decisions else 0
    b_skip_hard_pct = (sum(baseline_skip_reasons[k] for k in HARD_CONSTRAINTS) / total_decisions * 100) if total_decisions else 0
    b_skip_gate_pct = (baseline_skip_reasons["simulator_feasibility_gate"] / total_decisions * 100) if total_decisions else 0

    baseline_dist_stats = {
        "n_accepted": len(baseline_distances_accepted),
        "mean_km": round(mean(baseline_distances_accepted), 3) if baseline_distances_accepted else 0,
        "p50_km": round(quantile(baseline_distances_accepted, 0.5), 3) if baseline_distances_accepted else 0,
        "p75_km": round(quantile(baseline_distances_accepted, 0.75), 3) if baseline_distances_accepted else 0,
        "p95_km": round(quantile(baseline_distances_accepted, 0.95), 3) if baseline_distances_accepted else 0,
    }

    # Determinism Verification on 3 seeds
    determinism_seeds = [20001, 20002, 20003]
    determinism_results = {}
    for seed in determinism_seeds:
        orig_b, orig_s = raw_results[seed]
        cfg = ShiftConfig(seed=seed, shift_hours=8, vehicle="moto", start_location_zone=7, profile=profile)
        rep_b, rep_s = run_pair_v3(cfg, model, policy, output=None, baseline_config=baseline_cfg)

        assert rep_b.stream_sha256 == orig_b.stream_sha256, f"Determinism stream mismatch baseline {seed}"
        assert rep_s.stream_sha256 == orig_s.stream_sha256, f"Determinism stream mismatch smart {seed}"

        # Logical events equality (ignores latency_ms)
        assert logical(rep_b.log.events) == logical(orig_b.log.events), f"Determinism baseline logic mismatch {seed}"
        assert logical(rep_s.log.events) == logical(orig_s.log.events), f"Determinism smart logic mismatch {seed}"

        assert math.isclose(rep_b.metrics.net_earnings_mxn, orig_b.metrics.net_earnings_mxn), f"Determinism baseline econ mismatch {seed}"
        assert math.isclose(rep_s.metrics.net_earnings_mxn, orig_s.metrics.net_earnings_mxn), f"Determinism smart econ mismatch {seed}"

        determinism_results[seed] = {
            "stream_sha256": rep_b.stream_sha256,
            "logical_events_identical": True,
            "economic_results_identical": True,
            "baseline_net": round(rep_b.metrics.net_earnings_mxn, 2),
            "smart_net": round(rep_s.metrics.net_earnings_mxn, 2),
        }

    summary_data = {
        "evaluation_name": "FirstNearbyOrderBaseline vs SmartAgent Evaluation",
        "seeds": REPORTING_SEEDS,
        "seed_count": len(REPORTING_SEEDS),
        "heldout_verified": True,
        "baseline_threshold_km": baseline_cfg.max_distance_km,
        "baseline_profile_version": baseline_cfg.profile_version,
        "shift_parameters": {
            "hours": 8,
            "vehicle": "moto",
            "start_zone": 7,
            "cost_per_km": 1.20,
        },
        "aggregate_economics": {
            "mean_baseline_net_mxn": round(mean_baseline_net, 2),
            "mean_smart_net_mxn": round(mean_smart_net, 2),
            "median_baseline_net_mxn": round(median_baseline_net, 2),
            "median_smart_net_mxn": round(median_smart_net, 2),
            "absolute_mean_difference_mxn": round(mean_smart_net - mean_baseline_net, 2),
            "mean_improvement_pct": round(mean_improvement_pct, 2),
            "median_improvement_pct": round(median_improvement_pct, 2),
            "smart_win_rate_pct": round(smart_win_rate, 2),
            "baseline_win_rate_pct": round(baseline_win_rate, 2),
            "tie_rate_pct": round(tie_rate, 2),
            "smart_wins": smart_wins,
            "baseline_wins": baseline_wins,
            "ties": ties,
        },
        "aggregate_operations": {
            "mean_baseline_completed": round(mean_baseline_completed, 2),
            "mean_smart_completed": round(mean_smart_completed, 2),
            "mean_baseline_distance_km": round(mean_baseline_distance, 2),
            "mean_smart_distance_km": round(mean_smart_distance, 2),
            "mean_baseline_late": round(mean_baseline_late, 2),
            "mean_smart_late": round(mean_smart_late, 2),
            "total_baseline_safety_violations": total_baseline_safety,
            "total_smart_safety_violations": total_smart_safety,
        },
        "decisions_analysis": {
            "total_decisions": total_decisions,
            "identical_decisions": total_identical,
            "percentage_identical": round(pct_identical, 2),
            "disagreements": total_disagreements,
            "percentage_disagreements": round(pct_disagreement, 2),
            "disagreement_breakdown": {
                "baseline_accept_smart_skip": b_acc_s_skip,
                "baseline_skip_smart_accept": b_skip_s_acc,
            },
        },
        "baseline_behavior": {
            "acceptance_rate_pct": round(b_accept_rate, 2),
            "skip_rate_pct": round(b_skip_rate, 2),
            "skip_breakdown_pct": {
                "distance_threshold": round(b_skip_distance_pct, 2),
                "hard_constraints": round(b_skip_hard_pct, 2),
                "simulator_feasibility_gate": round(b_skip_gate_pct, 2),
            },
            "skip_counts": dict(baseline_skip_reasons),
            "accepted_distance_km": baseline_dist_stats,
        },
        "determinism_verification": {
            "tested_seeds": determinism_seeds,
            "status": "PASS",
            "details": determinism_results,
        },
        "safety_audit": {
            "status": "PASS",
            "violations": 0,
        },
    }

    # Write CSV results
    csv_results_path = OUT / "baseline_vs_smart_results.csv"
    with csv_results_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results_table[0].keys()))
        writer.writeheader()
        writer.writerows(results_table)

    # Write JSON summary
    json_summary_path = OUT / "baseline_vs_smart_summary.json"
    json_summary_path.write_text(json.dumps(summary_data, indent=2) + "\n")

    # Write CSV decision diffs
    csv_diff_path = OUT / "baseline_vs_smart_decision_diff.csv"
    if decision_diffs:
        with csv_diff_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(decision_diffs[0].keys()))
            writer.writeheader()
            writer.writerows(decision_diffs)

    print(f"Results written to {csv_results_path}")
    print(f"Summary written to {json_summary_path}")
    print(f"Decision diffs written to {csv_diff_path}")
    print("Aggregate Economics:")
    print(json.dumps(summary_data["aggregate_economics"], indent=2))
    return summary_data, results_table, decision_diffs


if __name__ == "__main__":
    run_evaluation()
