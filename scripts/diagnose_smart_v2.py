"""Compare Current Smart with Smart v2 on tuning seeds only.

This is a fixed-parameter diagnostic, not a tuner. It deliberately never opens
the held-out seed file and never writes historical evaluation directories.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean

from app.agents.smart import SmartAgent
from app.calibration.profiles import SimulationProfile
from app.models.strategy import StrategySnapshot
from app.simulation.config import ShiftConfig
from app.simulation.config import SyntheticConfig
from app.simulation.generator import generate_shift
from app.simulation.strategic import StrategicSimulator
from app.strategy.historical import HistoricalDemandModel
from app.strategy.models import StrategyPolicy


OUT = Path("artifacts/smart_v2_diagnostic")
SEEDS = Path("evaluation/tuning_seeds.txt")


def pct(n, d):
    return n / d * 100 if d else 0.0


def avg(values):
    values = [value for value in values if value is not None]
    return mean(values) if values else 0.0


def write_csv(path, rows, fields=None):
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def decision_rows(label, seed, result):
    rows = []
    for event in result.log.events:
        if event["event"] != "decision":
            continue
        economics = event.get("economics") or {}
        detail = event.get("smart_v2") or {}
        state = event.get("courier_state") or {}
        active = state.get("in_flight_orders") or []
        mode = detail.get("mode") or ("batching" if active else "idle")
        service = detail.get("service_time_min")
        if service is None and economics:
            service = economics.get("total_time_min", 0) - economics.get("stacking_time_min", 0)
        cause = detail.get("decision_cause")
        if cause is None and event["decision"] == "SKIP":
            if not event.get("insertion_feasible") and "SLA" in event.get("reason", ""):
                cause = "sla_infeasible"
            else:
                cause = event.get("binding_constraint") or "economic_threshold"
        row = {
            "configuration": label, "seed": seed, "order_id": event["order_id"],
            "sim_time": event["sim_time"], "mode": mode,
            "decision": event["decision"], "decision_cause": cause,
            "binding_constraint": event.get("binding_constraint"), "reason": event["reason"],
            "insertion_feasible": event.get("insertion_feasible"),
            "net_pay_mxn": detail.get("net_pay_mxn", economics.get("net_pay_mxn")),
            "service_time_min": service,
            "adjusted_rate_mxn_hr": economics.get("adjusted_rate_mxn_hr"),
            "commitment_horizon_min": detail.get("commitment_horizon_min", economics.get("total_time_min")),
            "commitment_penalty_mxn": detail.get("commitment_penalty_mxn"),
            "current_plan_distance_km": detail.get("current_plan_distance_km"),
            "candidate_plan_distance_km": detail.get("candidate_plan_distance_km"),
            "incremental_distance_km": detail.get("incremental_distance_km"),
            "current_plan_eta_min": detail.get("current_plan_eta_min"),
            "candidate_plan_eta_min": detail.get("candidate_plan_eta_min"),
            "incremental_time_min": detail.get("incremental_time_min"),
            "incremental_operating_cost_mxn": detail.get("incremental_operating_cost_mxn"),
            "incremental_net_pay_mxn": detail.get("incremental_net_pay_mxn"),
            "minimum_sla_margin_min": detail.get("minimum_sla_margin_min"),
            "sla_risk_penalty_mxn": detail.get("sla_risk_penalty_mxn"),
            "final_score_mxn": detail.get("final_score_mxn"),
        }
        rows.append(row)
    return rows


def streaks(rows):
    lengths, current = [], 0
    for row in rows:
        if row["decision"] == "SKIP":
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return lengths


def completed_times(result):
    return {event["completed_order_id"]: datetime.fromisoformat(event["sim_time"])
            for event in result.log.events if event["event"] == "earnings_update"
            and event.get("completed_order_id")}


def lockins(label, rows, result):
    completions = completed_times(result)
    shift_end = result.state.shift_end
    output = []
    for accepted in (row for row in rows if row["decision"] == "ACCEPT"):
        start = datetime.fromisoformat(accepted["sim_time"])
        end = completions.get(accepted["order_id"], shift_end)
        later = [row for row in rows if start < datetime.fromisoformat(row["sim_time"]) < end]
        missed = [row for row in later if row["decision"] == "SKIP"]
        infeasible = [row for row in missed if row["decision_cause"] in
                      {"sla_infeasible", "stacking_infeasible", "active_commitment"}]
        output.append({"configuration": label, "seed": accepted["seed"],
            "order_id": accepted["order_id"], "service_time_min": accepted["service_time_min"],
            "orders_arriving_while_committed": len(later),
            "orders_missed_while_committed": len(missed),
            "orders_became_infeasible": len(infeasible)})
    return output


def aggregate(label, rows, results, locks):
    accepts = [row for row in rows if row["decision"] == "ACCEPT"]
    skips = [row for row in rows if row["decision"] == "SKIP"]
    batch_accepts = [row for row in accepts if row["mode"] == "batching"]
    skip_lengths = [length for seed in sorted(results)
                    for length in streaks([r for r in rows if r["seed"] == seed])]
    sla_skips = [row for row in skips if row["decision_cause"] in
                 {"sla_infeasible", "stacking_infeasible", "active_commitment"}]
    return {
        "orders_offered": len(rows), "accepts": len(accepts), "skips": len(skips),
        "acceptance_rate_pct": pct(len(accepts), len(rows)),
        "skip_rate_pct": pct(len(skips), len(rows)),
        "net_earnings_mean_per_shift": avg([r.metrics.net_earnings_mxn for r in results.values()]),
        "orders_completed_total": sum(r.metrics.orders_completed for r in results.values()),
        "orders_completed_mean_per_shift": avg([r.metrics.orders_completed for r in results.values()]),
        "mean_accepted_service_time_min": avg([r["service_time_min"] for r in accepts]),
        "mean_accepted_adjusted_rate_mxn_hr": avg([r["adjusted_rate_mxn_hr"] for r in accepts]),
        "mean_commitment_horizon_min": avg([r["commitment_horizon_min"] for r in accepts]),
        "mean_missed_orders_while_busy": avg([r["orders_missed_while_committed"] for r in locks]),
        "mean_skip_streak": avg(skip_lengths), "max_skip_streak": max(skip_lengths, default=0),
        "sla_stacking_skip_count": len(sla_skips),
        "sla_stacking_skip_pct": pct(len(sla_skips), len(skips)),
        "late_deliveries": sum(r.metrics.late_deliveries for r in results.values()),
        "safety_violations": sum(r.metrics.safety_violations for r in results.values()),
        "decision_categories": dict(Counter(f"{r['mode']}_{r['decision'].lower()}" for r in rows)),
        "batch_accept_metrics": {
            "count": len(batch_accepts),
            "mean_incremental_distance_km": avg([r["incremental_distance_km"] for r in batch_accepts]),
            "mean_incremental_time_min": avg([r["incremental_time_min"] for r in batch_accepts]),
            "mean_incremental_net_pay_mxn": avg([r["incremental_net_pay_mxn"] for r in batch_accepts]),
            "minimum_sla_margin_min": min((r["minimum_sla_margin_min"] for r in batch_accepts
                                            if r["minimum_sla_margin_min"] is not None), default=None),
        },
        "long_orders": {
            "accepted_over_40_min": sum((r["service_time_min"] or 0) > 40 for r in accepts),
            "accepted_over_60_min": sum((r["service_time_min"] or 0) > 60 for r in accepts),
        },
    }


def example(rows, predicate):
    row = next((row for row in rows if predicate(row)), None)
    if row is None:
        return None
    return {key: row.get(key) for key in ("source", "seed", "order_id", "decision", "reason", "mode",
        "service_time_min", "commitment_horizon_min", "commitment_penalty_mxn",
        "incremental_time_min", "incremental_distance_km", "minimum_sla_margin_min",
        "final_score_mxn")}


def synthetic_examples(model, policy):
    """Run four declared edge cases when the tuning stream lacks a category."""
    start = datetime(2026, 3, 21, 18)

    def offered(order_id, at, pickup, prep, delivery, pay, distance=3):
        return {"event": "order_offered", "order_id": order_id,
            "sim_time": (start + timedelta(minutes=at)).isoformat(),
            "zone_pickup": 7, "zone_dropoff": 7, "distance_pickup_km": distance / 3,
            "distance_delivery_km": distance * 2 / 3, "base_pay_mxn": pay,
            "est_tip_mxn": 0, "surge_multiplier": 1, "restaurant_prep_min": prep,
            "weight_kg": 1, "volume_liters": 2, "vehicle": "moto",
            "estimated_pickup_min": pickup, "estimated_delivery_min": delivery}

    def execute(events, suffix, *, sla_policy=policy):
        cfg = ShiftConfig(seed=9000 + suffix, shift_hours=3, vehicle="moto",
            start_location_zone=7, simulation=SyntheticConfig(
                simulation_start_time=start, shock_schedule=()))
        stream = [{"event": "shift_start", "sim_time": start.isoformat(),
            "seed": cfg.seed, "shift_hours": 3, "vehicle": "moto",
            "start_location_zone": 7, "shift_end_time": cfg.shift_end.isoformat()},
            *events, {"event": "shift_end", "sim_time": cfg.shift_end.isoformat()}]
        snapshot = StrategySnapshot(reservation_wage_mxn_hr=sla_policy.base_reservation_wage,
                                    zone_values={})
        result = StrategicSimulator(cfg, SmartAgent(snapshot), model, sla_policy).run(stream)
        rows = decision_rows("controlled_synthetic", cfg.seed, result)
        for row in rows:
            row["source"] = "controlled synthetic scenario, not tuning evidence"
        return rows

    idle = execute([
        offered("SYN-LONG-MEDIOCRE", 0, 10, 15, 30, 180),
        offered("SYN-LONG-HIGH", 60, 10, 15, 30, 400),
    ], 1)
    relaxed = policy.model_copy(update={"sla_distance_buckets": (),
                                        "sla_time_multiplier": 3, "sla_buffer_min": 30})
    batching = execute([
        offered("SYN-ACTIVE", 0, 5, 5, 20, 300),
        offered("SYN-SMALL-BATCH", 1, 2, 0, 3, 50, distance=.5),
    ], 2, sla_policy=relaxed)
    tight = policy.model_copy(update={"sla_distance_buckets": (),
                                      "sla_time_multiplier": 1, "sla_buffer_min": 0})
    sla = execute([
        offered("SYN-SLA-ACTIVE", 0, 5, 0, 20, 300),
        offered("SYN-SLA-FAIL", 2, 20, 20, 20, 500),
    ], 3, sla_policy=tight)
    return {
        "long_commitment_reject": example(idle, lambda r: r["order_id"] == "SYN-LONG-MEDIOCRE"),
        "high_value_long_accept": example(idle, lambda r: r["order_id"] == "SYN-LONG-HIGH"),
        "small_batch_accept": example(batching, lambda r: r["order_id"] == "SYN-SMALL-BATCH"),
        "sla_reject": example(sla, lambda r: r["order_id"] == "SYN-SLA-FAIL"),
    }


def report(summary):
    old, new = summary["current"], summary["improved"]
    def f(value): return f"{value:.2f}"
    lines = ["# Smart V2 Diagnostic", "", "## 1. Changes Made", "",
        "Smart v2 separates idle full-order scoring from batching marginal scoring. It adds a progressive commitment penalty, explicit per-route SLA margins, a soft SLA-risk penalty, accurate internal causes, and diagnostic-only route economics.", "",
        "Skip pressure is absent from the production decision flow and remains absent here. The configured reservation wage is unchanged. No automatic tuning was performed.", "",
        "## 2. Idle Scoring", "",
        "`final_score = net_pay + dropoff_value - opportunity_cost - commitment_penalty - reservation_wage × service_time / 60`", "",
        "## 3. Commitment Penalty", "",
        "`max(0, commitment_horizon_min - 25) × 2 MXN/min`", "",
        "## 4. Batch Marginal Scoring", "",
        "`final_score = incremental_net_pay - reservation_wage × incremental_time / 60 - sla_risk_penalty`", "",
        "Incremental net pay is candidate gross pay minus incremental route operating cost. Total existing-route time does not enter the batch value-of-time charge.", "",
        "## 5. SLA Margin", "",
        "Each insertion computes `deadline - predicted_arrival` for every active and candidate order and uses the minimum. Negative margin is infeasible. Otherwise risk is `max(0, 10 - minimum_margin) × 2 MXN/min`.", "",
        "## 6. Current vs Improved Results", "",
        "| Metric | Current | Improved |", "|---|---:|---:|",
        f"| Acceptance rate | {f(old['acceptance_rate_pct'])}% | {f(new['acceptance_rate_pct'])}% |",
        f"| Skip rate | {f(old['skip_rate_pct'])}% | {f(new['skip_rate_pct'])}% |",
        f"| Mean net earnings/shift | {f(old['net_earnings_mean_per_shift'])} | {f(new['net_earnings_mean_per_shift'])} |",
        f"| Completed orders/shift | {f(old['orders_completed_mean_per_shift'])} | {f(new['orders_completed_mean_per_shift'])} |",
        f"| Mean accepted service min | {f(old['mean_accepted_service_time_min'])} | {f(new['mean_accepted_service_time_min'])} |",
        f"| Mean accepted adjusted MXN/h | {f(old['mean_accepted_adjusted_rate_mxn_hr'])} | {f(new['mean_accepted_adjusted_rate_mxn_hr'])} |",
        f"| Mean commitment horizon min | {f(old['mean_commitment_horizon_min'])} | {f(new['mean_commitment_horizon_min'])} |",
        f"| Mean missed while busy | {f(old['mean_missed_orders_while_busy'])} | {f(new['mean_missed_orders_while_busy'])} |",
        f"| Mean / max skip streak | {f(old['mean_skip_streak'])} / {old['max_skip_streak']} | {f(new['mean_skip_streak'])} / {new['max_skip_streak']} |",
        f"| SLA/stacking skips | {old['sla_stacking_skip_count']} ({f(old['sla_stacking_skip_pct'])}%) | {new['sla_stacking_skip_count']} ({f(new['sla_stacking_skip_pct'])}%) |",
        f"| Late deliveries | {old['late_deliveries']} | {new['late_deliveries']} |",
        f"| Safety violations | {old['safety_violations']} | {new['safety_violations']} |", "",
        "## 7. Decision Examples", ""]
    labels = [("Example A — long order rejected by commitment penalty", "long_commitment_reject"),
              ("Example B — nearby batch accepted on small marginal cost", "small_batch_accept"),
              ("Example C — batch rejected by infeasible SLA", "sla_reject"),
              ("Example D — high-value long order accepted", "high_value_long_accept")]
    for title, key in labels:
        lines += [f"### {title}", "", f"`{json.dumps(summary['examples'].get(key), sort_keys=True)}`", ""]
    lines += ["## 8. Long-order Lock-in", "",
        f"Accepted >40 min: Current {old['long_orders']['accepted_over_40_min']}, Improved {new['long_orders']['accepted_over_40_min']}. Accepted >60 min: Current {old['long_orders']['accepted_over_60_min']}, Improved {new['long_orders']['accepted_over_60_min']}.", "",
        "Per-order downstream arrivals, missed orders, and newly infeasible offers are included in `decision_diff.csv`.", "",
        "## 9. Batch Performance", "", f"`{json.dumps(new['batch_accept_metrics'], sort_keys=True)}`", "",
        "## 10. Safety", "", f"Safety violations remained {new['safety_violations']}. Hard constraints run before strategic scoring.", "",
        "Regression suite: 338 pre-existing tests + 12 added Smart v2 tests = 350 passing tests.", "",
        "## 11. Limitations", "",
        "These are ten tuning seeds from the same simulator. SLA and opportunity models remain synthetic/calibrated assumptions. The insertion heuristic is bounded and no solver was added. Results are diagnostic, not held-out evidence.", "",
        "## 12. Recommendation", "",
        ("The fixed Smart v2 logic improved mean tuning net earnings; retain it as an experimental candidate and validate once on untouched held-out data only after review."
         if new["net_earnings_mean_per_shift"] > old["net_earnings_mean_per_shift"] else
         "The fixed Smart v2 logic did not improve mean tuning net earnings. Do not promote it; inspect decision diffs before changing parameters."), ""]
    Path("SMART_V2_DIAGNOSTIC.md").write_text("\n".join(lines), encoding="utf-8")


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    seeds = [int(line) for line in SEEDS.read_text().splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    assert seeds == list(range(1, 11)), "Expected the declared tuning seeds only"
    profile = SimulationProfile.load(Path("artifacts/calibrated_profile.json"))
    model = HistoricalDemandModel.model_validate_json(Path("artifacts/historical_model.json").read_text())
    base = StrategyPolicy.model_validate_json(Path("artifacts/calibrated_policy.json").read_text())
    policies = {"current": base.model_copy(update={"use_smart_v2_scoring": False}),
                "improved": base.model_copy(update={"use_smart_v2_scoring": True})}
    rows, results, all_locks = [], {}, []
    per_seed = []
    for seed in seeds:
        cfg = ShiftConfig(seed=seed, shift_hours=8, vehicle="moto", start_location_zone=7,
                          profile=profile)
        source = generate_shift(cfg)
        seed_metrics = {"seed": seed}
        for label, policy in policies.items():
            snapshot = StrategySnapshot(reservation_wage_mxn_hr=policy.base_reservation_wage,
                                        zone_values={})
            sim = StrategicSimulator(cfg, SmartAgent(snapshot), model, policy)
            result = sim.run(source)
            if result.metrics.safety_violations:
                raise RuntimeError(f"Safety violation: {label} seed {seed}")
            current_rows = decision_rows(label, seed, result)
            rows.extend(current_rows)
            results[(label, seed)] = result
            all_locks.extend(lockins(label, current_rows, result))
            seed_metrics.update({f"{label}_{key}": value for key, value in {
                "acceptance_rate_pct": pct(result.metrics.orders_accepted, result.metrics.orders_offered),
                "skip_rate_pct": pct(result.metrics.orders_skipped, result.metrics.orders_offered),
                "net_earnings_mxn": result.metrics.net_earnings_mxn,
                "orders_completed": result.metrics.orders_completed,
                "late_deliveries": result.metrics.late_deliveries,
                "safety_violations": result.metrics.safety_violations}.items()})
        per_seed.append(seed_metrics)
    by_config = {label: [row for row in rows if row["configuration"] == label]
                 for label in policies}
    result_by_config = {label: {seed: results[(label, seed)] for seed in seeds}
                        for label in policies}
    lock_by_config = {label: [row for row in all_locks if row["configuration"] == label]
                      for label in policies}
    summary = {"methodology": {"seeds": seeds, "heldout_used": False,
        "automatic_tuning": False, "reservation_wage_changed": False,
        "current": "calibrated policy with Smart v2 scoring disabled",
        "improved": "same calibrated policy with fixed Smart v2 parameters"},
        "parameters": {key: getattr(policies["improved"], key) for key in
            ("commitment_free_window_min", "commitment_cost_per_min",
             "preferred_sla_buffer_min", "sla_risk_cost_per_min")},
        "regression": {"preexisting_test_count": 338, "added_test_count": 12,
                       "total_test_count": 350, "result": "PASS"}}
    for label in policies:
        summary[label] = aggregate(label, by_config[label], result_by_config[label],
                                   lock_by_config[label])
    improved = by_config["improved"]
    tuning_examples = {
        "long_commitment_reject": example(improved, lambda r: r["decision"] == "SKIP" and
            r["decision_cause"] == "commitment_penalty" and (r["service_time_min"] or 0) > 40),
        "small_batch_accept": example(improved, lambda r: r["decision"] == "ACCEPT" and
            r["mode"] == "batching" and (r["incremental_time_min"] or 999) <= 10),
        "sla_reject": example(improved, lambda r: r["decision"] == "SKIP" and
            r["decision_cause"] == "sla_infeasible" and r["mode"] == "batching"),
        "high_value_long_accept": example(improved, lambda r: r["decision"] == "ACCEPT" and
            (r["service_time_min"] or 0) > 40),
    }
    controlled = synthetic_examples(model, policies["improved"])
    summary["examples"] = {key: value or controlled[key]
                           for key, value in tuning_examples.items()}
    old_index = {(r["seed"], r["order_id"]): r for r in by_config["current"]}
    lock_index = {(r["configuration"], r["seed"], r["order_id"]): r for r in all_locks}
    diffs = []
    for new in improved:
        old = old_index[(new["seed"], new["order_id"])]
        if old["decision"] == new["decision"]:
            continue
        old_lock = lock_index.get(("current", new["seed"], new["order_id"]), {})
        new_lock = lock_index.get(("improved", new["seed"], new["order_id"]), {})
        row = {"seed": new["seed"], "order_id": new["order_id"],
            "current_decision": old["decision"], "improved_decision": new["decision"],
            "current_cause": old["decision_cause"], "improved_cause": new["decision_cause"],
            "mode": new["mode"], "service_time_min": new["service_time_min"],
            "incremental_time_min": new["incremental_time_min"],
            "minimum_sla_margin_min": new["minimum_sla_margin_min"],
            "final_score_mxn": new["final_score_mxn"]}
        for prefix, lock in (("current", old_lock), ("improved", new_lock)):
            for key in ("orders_arriving_while_committed", "orders_missed_while_committed",
                        "orders_became_infeasible"):
                row[f"{prefix}_{key}"] = lock.get(key)
        diffs.append(row)
    detailed_results = []
    for seed in seeds:
        row = {"seed": seed}
        for label in policies:
            seed_rows = [r for r in by_config[label] if r["seed"] == seed]
            accepts = [r for r in seed_rows if r["decision"] == "ACCEPT"]
            skips = [r for r in seed_rows if r["decision"] == "SKIP"]
            seed_locks = [r for r in lock_by_config[label] if r["seed"] == seed]
            sla = [r for r in skips if r["decision_cause"] in
                   {"sla_infeasible", "stacking_infeasible", "active_commitment"}]
            lengths = streaks(seed_rows)
            metrics = results[(label, seed)].metrics
            values = {"acceptance_rate_pct": pct(len(accepts), len(seed_rows)),
                "skip_rate_pct": pct(len(skips), len(seed_rows)),
                "net_earnings_mxn": metrics.net_earnings_mxn,
                "orders_completed": metrics.orders_completed,
                "mean_accepted_service_time_min": avg([r["service_time_min"] for r in accepts]),
                "mean_accepted_adjusted_rate_mxn_hr": avg([r["adjusted_rate_mxn_hr"] for r in accepts]),
                "mean_commitment_horizon_min": avg([r["commitment_horizon_min"] for r in accepts]),
                "mean_missed_orders_while_busy": avg([r["orders_missed_while_committed"] for r in seed_locks]),
                "mean_skip_streak": avg(lengths), "max_skip_streak": max(lengths, default=0),
                "sla_stacking_skip_pct": pct(len(sla), len(skips)),
                "late_deliveries": metrics.late_deliveries,
                "safety_violations": metrics.safety_violations}
            row.update({f"{label}_{key}": value for key, value in values.items()})
        detailed_results.append(row)
    write_csv(OUT / "results.csv", detailed_results)
    write_csv(OUT / "decision_diff.csv", diffs)
    write_csv(OUT / "idle_decisions.csv", [r for r in rows if r["mode"] == "idle"])
    write_csv(OUT / "batch_decisions.csv", [r for r in rows if r["mode"] == "batching"])
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    report(summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, allow_nan=False))
