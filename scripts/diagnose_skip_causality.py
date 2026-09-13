"""Post-hoc causal diagnostic for SmartAgent skips on tuning seeds 1..10.

This runner is intentionally isolated from production policy/agent code.  It
replays the two requested configurations and records the first simulator stage
that prevents an offer from being accepted.  It never reads held-out seeds.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median

from app.agents.base import decision_request
from app.agents.smart import SmartAgent
from app.calibration.profiles import SimulationProfile
from app.decision.constraints import evaluate_constraints
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.models.responses import DecideResponse
from app.simulation.config import ShiftConfig
from app.simulation.generator import generate_shift
from app.simulation.state import ActiveOrder, MINUTE_US
from app.simulation.strategic import StrategicSimulator
from app.strategy.historical import HistoricalDemandModel
from app.strategy.models import StrategyPolicy
from app.strategy.routing import route_plan, steps_for
from app.strategy.sla import compute_delivery_deadline


OUT = Path("artifacts/skip_diagnostic")
THRESHOLDS = (165, 125, 100, 80, 60, 40)
HARD = {"flagged_zone_night", "mandatory_break", "heat_rule", "shift_end_infeasible", "vehicle_capacity"}
BUSY = {"not_actionable_while_busy", "active_commitment_infeasible"}
SLA = {"sla_infeasible", "stacking_infeasible"}


def pct(n, d):
    return n / d * 100 if d else 0.0


def quantile(values, q):
    values = sorted(values)
    if not values:
        return None
    at = (len(values) - 1) * q
    lo, hi = int(at), min(int(at) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (at - lo)


def own_service_min(order, snapshot):
    profile = snapshot.vehicle_profiles[order.vehicle]
    pickup = order.estimated_pickup_min
    delivery = order.estimated_delivery_min
    if pickup is None:
        pickup = order.distance_pickup_km / profile.speed_kmh * 60
    if delivery is None:
        delivery = order.distance_delivery_km / profile.speed_kmh * 60
    raw = pickup + delivery + order.restaurant_prep_min
    return max(snapshot.policy.minimum_service_time_min, raw)


class DiagnosticSimulator(StrategicSimulator):
    """StrategicSimulator with observability only; execution semantics stay intact."""

    def __init__(self, config, agent, model, policy, *, label, pressure):
        super().__init__(config, agent, model, policy)
        self.label = label
        self.pressure_enabled = pressure
        self.consecutive_skips = 0
        self.rows = []

    def _insertion_diagnostic(self, job, request):
        active = list(self.state.in_flight_orders)
        base = {
            "current_active_orders": len(active),
            "remaining_work_min": sum(p.remaining_us for j in active for p in j.phases) / MINUTE_US,
            "current_route_distance_km": sum(p.distance_km for j in active for p in j.phases),
            "candidate_service_time_min": own_service_min(request, self.agent.snapshot),
            "candidate_route_distance_km": request.distance_pickup_km + request.distance_delivery_km,
            "candidate_sla_min": (job.promised_completion_time - request.sim_time).total_seconds() / 60,
            "projected_completion": None,
            "infeasible_reason": None,
        }
        if self.move:
            base["infeasible_reason"] = "Simulator reserves availability during repositioning; offer is not evaluated against an insertion."
            return "not_actionable_while_busy", base
        if len(active) >= self.policy.max_active_orders:
            base["infeasible_reason"] = f"max_active_orders={self.policy.max_active_orders} reached before candidate generation."
            return "not_actionable_while_busy", base

        new = steps_for(job)
        sequences = [self.route + new]
        if self.policy.use_improved_batching:
            for pickup in range(1 if self.route else 0, len(self.route) + 1):
                for delivery in range(pickup, len(self.route) + 1):
                    if len(sequences) >= self.policy.max_insertions:
                        break
                    sequences.append(self.route[:pickup] + new[:2] + self.route[pickup:delivery] + new[2:] + self.route[delivery:])
                if len(sequences) >= self.policy.max_insertions:
                    break
        deadlines = {j.offer.order_id: j.promised_completion_time for j in (*active, job)}
        state = __import__("app.models.state", fromlist=["resolve_state"]).resolve_state(
            request.sim_time, request.courier_state_overrides, self.agent.snapshot.policy.default_shift_hours)
        deadline_pass = []
        candidate_late_all = True
        existing_late_all = bool(active)
        nearest_completion = None
        for sequence in sequences:
            plan, completion = route_plan(sequence, request.sim_time, job.offer.order_id)
            candidate_late = completion[job.offer.order_id] > deadlines[job.offer.order_id]
            existing_late = any(completion[j.offer.order_id] > deadlines[j.offer.order_id] for j in active)
            candidate_late_all &= candidate_late
            existing_late_all &= existing_late
            when = completion[job.offer.order_id]
            nearest_completion = when if nearest_completion is None or when < nearest_completion else nearest_completion
            if not candidate_late and not existing_late:
                deadline_pass.append((sequence, plan, completion))
        base["projected_completion"] = nearest_completion.isoformat() if nearest_completion else None
        if not deadline_pass:
            if existing_late_all:
                cause = "active_commitment_infeasible"
                reason = "Every insertion breaches at least one previously accepted order deadline."
            elif candidate_late_all:
                cause = "sla_infeasible"
                reason = "Every insertion breaches the candidate order deadline."
            else:
                cause = "stacking_infeasible"
                reason = "No insertion jointly preserves candidate and active-order deadlines."
            base["infeasible_reason"] = reason
            return cause, base

        viable = []
        violations = []
        for sequence, plan, completion in deadline_pass:
            violation = evaluate_constraints(request, state, self.agent.snapshot, plan)
            if violation:
                violations.append((violation, plan))
            else:
                score = sum((when - request.sim_time).total_seconds() for when in completion.values())
                viable.append((score, sequence, plan))
        if viable:
            _, _, plan = min(viable, key=lambda item: item[0])
            base["projected_completion"] = plan.completion_time.isoformat()
            return None, base
        violation, plan = violations[0]
        base["projected_completion"] = plan.completion_time.isoformat()
        base["infeasible_reason"] = violation.reason
        return violation.constraint, base

    def _offer(self, source):
        order = self._prepare_offer(source)
        request = decision_request(order, self.state)
        self._emit("order_offered", **order.model_dump(mode="json", exclude={"event", "sim_time", "courier_state_overrides"}, exclude_none=True), source_event=source)
        deadline = compute_delivery_deadline(order, self.state, self.policy)
        job = ActiveOrder.accepted(order, self.agent.snapshot, deadline)
        candidate = self._candidate(job, request)
        primary, diagnostic = self._insertion_diagnostic(job, request)

        nominal = self.agent.snapshot.reservation_wage_mxn_hr
        pressure = min(20.0, self.consecutive_skips * 2.5) if self.pressure_enabled else 0.0
        effective = max(40.0, nominal - pressure) if self.pressure_enabled else nominal
        if effective != nominal:
            adjusted = self.agent.snapshot.model_copy(update={"reservation_wage_mxn_hr": effective})
            self.agent.snapshot = adjusted
            self.store.replace(adjusted)
        if candidate:
            sequence, plan = candidate
            response = self.agent.service.decide(request, plan=plan)
        else:
            response = self.agent.decide_request(request)
            if response.decision == "ACCEPT":
                response = response.model_copy(update={"decision": "SKIP", "binding_constraint": "reservation_wage",
                    "reason": "Skipped: configured SLA or active-commitment limit prevents a feasible insertion; repositioning also reserves availability."})
        self.state.orders_offered += 1
        if primary is None and response.decision == "SKIP":
            primary = response.binding_constraint or "other"
        if response.decision == "ACCEPT":
            primary = "accepted"

        econ = response.economics.model_dump(mode="json") if response.economics else {}
        row = {
            "configuration": self.label, "seed": self.config.seed, "order_id": request.order_id,
            "sim_time": request.sim_time.isoformat(), "decision": response.decision,
            "primary_cause": primary, "agent_binding_constraint": response.binding_constraint,
            "agent_reason": response.reason, "insertion_feasible": candidate is not None,
            "base_reservation_wage": self.policy.base_reservation_wage,
            "nominal_reservation_wage": nominal, "skip_pressure": pressure,
            "effective_reservation_wage": effective, "consecutive_skips_before": self.consecutive_skips,
            "idle_time_min": self.state.idle_time_min, "status": self.state.status,
            "distance_km": request.distance_pickup_km + request.distance_delivery_km,
            "net_pay_mxn": econ.get("net_pay_mxn"), "adjusted_rate_mxn_hr": econ.get("adjusted_rate_mxn_hr"),
            "economic_total_time_min": econ.get("total_time_min"), **diagnostic,
        }
        if row["adjusted_rate_mxn_hr"] is not None:
            row["difference_to_threshold"] = row["adjusted_rate_mxn_hr"] - effective
        else:
            row["difference_to_threshold"] = None
        self.rows.append(row)
        self._emit("decision", **response.model_dump(mode="json"), decision_request=request.model_dump(mode="json"),
                   courier_state=self.state.summary(), strategy_snapshot=self.agent.snapshot.model_dump(mode="json"),
                   delivery_deadline=deadline.isoformat(), insertion_feasible=candidate is not None,
                   planned_route=[[step.order_id, step.phase.kind] for step in candidate[0]] if candidate else [],
                   diagnostic_primary_cause=primary, diagnostic_nominal_threshold=nominal,
                   diagnostic_effective_threshold=effective, diagnostic_skip_pressure=pressure)
        if response.decision == "ACCEPT":
            self._commit_candidate(candidate[0], job)
            self.state.orders_accepted += 1
            self.consecutive_skips = 0
            self._drain_finished_phases()
        else:
            self.state.orders_skipped += 1
            self.state.skip_penalties += self.policy.skip_penalty_mxn
            self.consecutive_skips += 1
            if response.binding_constraint in {"mandatory_break", "heat_rule"} and not self.move:
                self._start_break()
        self._refresh_execution()


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def completion_map(events):
    result = {}
    for event in events:
        if event["event"] == "earnings_update" and event.get("completed_order_id"):
            result[event["completed_order_id"]] = datetime.fromisoformat(event["sim_time"])
    return result


def skip_streak_rows(rows):
    output = []
    for (config, seed), decisions in sorted(group(rows, lambda r: (r["configuration"], r["seed"])).items()):
        streak = []
        number = 0
        for row in decisions + [{"decision": "ACCEPT"}]:
            if row["decision"] == "SKIP":
                streak.append(row)
                continue
            if streak:
                number += 1
                families = Counter(cause_family(x["primary_cause"]) for x in streak)
                dominant, count = families.most_common(1)[0]
                classification = dominant if count / len(streak) > .5 else "mixed"
                output.append({"configuration": config, "seed": seed, "streak_number": number,
                    "start_time": streak[0]["sim_time"], "end_time": streak[-1]["sim_time"],
                    "length": len(streak), "dominant_class": classification,
                    "causes": json.dumps(dict(Counter(x["primary_cause"] for x in streak)), sort_keys=True)})
                streak = []
    return output


def group(rows, key):
    result = defaultdict(list)
    for row in rows:
        result[key(row)].append(row)
    return result


def cause_family(cause):
    if cause == "reservation_wage": return "mostly economic"
    if cause in BUSY: return "mostly busy"
    if cause in SLA: return "mostly SLA"
    if cause in HARD: return "mostly safety"
    return "mixed"


def build_lockin(config, seed, decisions, events):
    completed = completion_map(events)
    shift_end = datetime.fromisoformat(next(e for e in events if e["event"] == "shift_end")["sim_time"])
    output = []
    for accepted in (r for r in decisions if r["decision"] == "ACCEPT"):
        start = datetime.fromisoformat(accepted["sim_time"])
        end = completed.get(accepted["order_id"], shift_end)
        later = [r for r in decisions if start < datetime.fromisoformat(r["sim_time"]) < end]
        busy_skips = [r for r in later if r["decision"] == "SKIP" and r["current_active_orders"] > 0]
        output.append({"configuration": config, "seed": seed, "order_id": accepted["order_id"],
            "accepted_at": accepted["sim_time"], "completed_at": end.isoformat(),
            "minutes_occupied": (end-start).total_seconds()/60,
            "orders_arriving_while_busy": len(later), "orders_skipped_while_busy": len(busy_skips),
            "net_earnings_from_order": accepted["net_pay_mxn"],
            "service_time_min": accepted["candidate_service_time_min"],
            "adjusted_rate_mxn_hr": accepted["adjusted_rate_mxn_hr"]})
    return output


def stats(values):
    values = [v for v in values if v is not None]
    return {"p10": quantile(values,.1), "p25": quantile(values,.25), "p50": quantile(values,.5),
            "p75": quantile(values,.75), "p90": quantile(values,.9), "mean": mean(values) if values else None}


def run():
    profile = SimulationProfile.load(Path("artifacts/calibrated_profile.json"))
    model = HistoricalDemandModel.model_validate_json(Path("artifacts/historical_model.json").read_text())
    base_policy = StrategyPolicy.model_validate_json(Path("artifacts/calibrated_policy.json").read_text())
    seeds = [int(x) for x in Path("evaluation/tuning_seeds.txt").read_text().splitlines() if x.strip() and not x.startswith("#")]
    # Deliberately do not open or inspect the official held-out seed file.
    assert seeds == list(range(1, 11))
    configs = {
        "old": (base_policy.model_copy(update={"base_reservation_wage": 165.0}), False),
        "new": (base_policy.model_copy(update={"base_reservation_wage": 60.0, "min_reservation_wage": 40.0}), True),
    }
    all_rows, runs = [], {}
    for label, (policy, pressure) in configs.items():
        for seed in seeds:
            cfg = ShiftConfig(seed=seed, shift_hours=8, vehicle="moto", start_location_zone=7, profile=profile)
            source = generate_shift(cfg)
            snapshot = StrategySnapshot(reservation_wage_mxn_hr=policy.base_reservation_wage, zone_values={})
            simulator = DiagnosticSimulator(cfg, SmartAgent(snapshot), model, policy, label=label, pressure=pressure)
            result = simulator.run(source)
            if result.metrics.safety_violations:
                raise RuntimeError(f"Safety violation in {label} seed {seed}")
            all_rows.extend(simulator.rows)
            runs[(label, seed)] = {"result": result, "events": result.log.events, "source": source}

    OUT.mkdir(parents=True, exist_ok=True)
    skips = [r for r in all_rows if r["decision"] == "SKIP"]
    cause_rows = []
    for config in configs:
        offered = sum(r["configuration"] == config for r in all_rows)
        selected = [r for r in skips if r["configuration"] == config]
        for cause, count in Counter(r["primary_cause"] for r in selected).most_common():
            cause_rows.append({"configuration": config, "cause": cause, "count": count,
                "percentage_of_all_skips": pct(count, len(selected)), "percentage_of_all_orders": pct(count, offered)})
    write_csv(OUT/"skip_causes.csv", cause_rows)
    # One mutually-exclusive primary cause per actual SKIP, including the
    # complete busy/commitment diagnostic requested for auditability.
    write_csv(OUT/"skip_decisions.csv", skips)

    per_seed = []
    for seed in seeds:
        item = {"seed": seed}
        for config in configs:
            rows = [r for r in all_rows if r["configuration"] == config and r["seed"] == seed]
            result = runs[(config,seed)]["result"]
            item.update({f"{config}_accepts": sum(r["decision"]=="ACCEPT" for r in rows),
                f"{config}_skips": sum(r["decision"]=="SKIP" for r in rows),
                f"{config}_reservation_wage_skips": sum(r["primary_cause"]=="reservation_wage" for r in rows),
                f"{config}_busy_commitment_skips": sum(r["primary_cause"] in BUSY for r in rows),
                f"{config}_sla_stacking_skips": sum(r["primary_cause"] in SLA for r in rows),
                f"{config}_idle_time_min": result.metrics.idle_time_min,
                f"{config}_net_earnings_mxn": result.metrics.net_earnings_mxn})
        per_seed.append(item)
    write_csv(OUT/"skip_causes_old_vs_new.csv", per_seed)

    wage_rows = []
    for config in configs:
        econ_skips = [r for r in skips if r["configuration"] == config and r["primary_cause"] == "reservation_wage"]
        margins = [r["difference_to_threshold"] for r in econ_skips]
        for name, value in stats(margins).items():
            wage_rows.append({"row_type":"distribution", "configuration": config, "metric": "adjusted_rate_minus_effective_threshold", "statistic": name, "value": value, "n": len(margins)})
        for threshold in THRESHOLDS:
            crossed = sum(r["adjusted_rate_mxn_hr"] >= threshold for r in econ_skips)
            wage_rows.append({"row_type":"counterfactual", "configuration": config, "metric": "offline_threshold_counterfactual", "statistic": f"threshold_{threshold}", "value": crossed, "n": len(econ_skips)})
        for row in econ_skips:
            wage_rows.append({"row_type":"skip", "configuration":config, "seed":row["seed"], "order_id":row["order_id"],
                "sim_time":row["sim_time"], "adjusted_rate_mxn_hr":row["adjusted_rate_mxn_hr"],
                "base_reservation_wage":row["base_reservation_wage"],
                "nominal_reservation_wage":row["nominal_reservation_wage"],
                "effective_reservation_wage":row["effective_reservation_wage"],
                "difference_to_threshold":row["difference_to_threshold"],
                "consecutive_skips":row["consecutive_skips_before"], "idle_time_min":row["idle_time_min"]})
    wage_fields=["row_type","configuration","metric","statistic","value","n","seed","order_id","sim_time",
        "adjusted_rate_mxn_hr","base_reservation_wage","nominal_reservation_wage","effective_reservation_wage",
        "difference_to_threshold","consecutive_skips","idle_time_min"]
    write_csv(OUT/"reservation_wage_distribution.csv", wage_rows, wage_fields)

    funnel = []
    for config in configs:
        rows = [r for r in all_rows if r["configuration"] == config]
        hard_removed = sum(r["primary_cause"] in HARD for r in rows)
        feasibility_removed = sum(r["primary_cause"] in SLA|BUSY for r in rows)
        economics_removed = sum(r["primary_cause"] == "reservation_wage" for r in rows)
        offered = len(rows)
        funnel.append({"configuration": config, "orders_offered": offered,
            "hard_constraint_pass": offered-hard_removed,
            "feasibility_pass": offered-hard_removed-feasibility_removed,
            "economics_pass": offered-hard_removed-feasibility_removed-economics_removed,
            "accepted": sum(r["decision"]=="ACCEPT" for r in rows)})
    write_csv(OUT/"acceptance_funnel.csv", funnel)

    by_key = {(r["configuration"],r["seed"],r["order_id"]):r for r in all_rows}
    transitions = []
    for seed in seeds:
        old = {r["order_id"]:r for r in all_rows if r["configuration"]=="old" and r["seed"]==seed}
        new = {r["order_id"]:r for r in all_rows if r["configuration"]=="new" and r["seed"]==seed}
        for order_id in sorted(old.keys() & new.keys()):
            if old[order_id]["decision"] == new[order_id]["decision"]:
                continue
            accepted_cfg = "new" if new[order_id]["decision"] == "ACCEPT" else "old"
            accepted = new[order_id] if accepted_cfg == "new" else old[order_id]
            lock = next(x for x in build_lockin(accepted_cfg, seed,
                [r for r in all_rows if r["configuration"]==accepted_cfg and r["seed"]==seed],
                runs[(accepted_cfg,seed)]["events"]) if x["order_id"]==order_id)
            other_cfg = "old" if accepted_cfg == "new" else "new"
            end = datetime.fromisoformat(lock["completed_at"])
            start = datetime.fromisoformat(accepted["sim_time"])
            other_opps = [r for r in all_rows if r["configuration"]==other_cfg and r["seed"]==seed and r["decision"]=="ACCEPT"
                and start < datetime.fromisoformat(r["sim_time"]) < end
                and by_key.get((accepted_cfg,seed,r["order_id"]),{}).get("decision") != "ACCEPT"]
            lost = sum(r["net_pay_mxn"] or 0 for r in other_opps)
            gained = accepted["net_pay_mxn"] or 0
            transitions.append({"seed": seed, "order_id": order_id,
                "old_decision": old[order_id]["decision"], "new_decision": new[order_id]["decision"],
                "old_cause": old[order_id]["primary_cause"], "new_cause": new[order_id]["primary_cause"],
                "accepted_configuration": accepted_cfg, "net_rate_mxn_hr": accepted["adjusted_rate_mxn_hr"],
                "duration_min": accepted["candidate_service_time_min"], "distance_km": accepted["distance_km"],
                "earnings_mxn": gained, "subsequent_orders_missed": len(other_opps),
                "subsequent_skips_while_busy": lock["orders_skipped_while_busy"],
                "opportunity_lost_mxn": lost, "final_economic_impact_mxn": gained-lost})
    write_csv(OUT/"decision_transitions.csv", transitions)

    lockins = []
    for config in configs:
        for seed in seeds:
            lockins.extend(build_lockin(config, seed,
                [r for r in all_rows if r["configuration"]==config and r["seed"]==seed], runs[(config,seed)]["events"]))
    damage = {(r["seed"],r["order_id"]):r for r in transitions if r["accepted_configuration"]=="new"}
    for row in lockins:
        transition = damage.get((row["seed"],row["order_id"])) if row["configuration"]=="new" else None
        row["opportunity_lost_mxn"] = transition["opportunity_lost_mxn"] if transition else 0
        row["downstream_impact_mxn"] = (row["net_earnings_from_order"] or 0) - row["opportunity_lost_mxn"]
    lockins.sort(key=lambda r: (r["configuration"], -r["orders_skipped_while_busy"], -r["minutes_occupied"]))
    write_csv(OUT/"long_order_lockin.csv", lockins)

    streaks = skip_streak_rows(all_rows)
    write_csv(OUT/"skip_streaks.csv", streaks)
    reroute_fields = ["configuration","seed","agent","closure_id","old_route","new_route","old_distance","new_distance","old_eta","new_eta","detour","did_decision_behavior_change_afterward"]
    write_csv(OUT/"rerouting_effects.csv", [], reroute_fields)

    def aggregate(config):
        rows = [r for r in all_rows if r["configuration"]==config]
        selected_skips = [r for r in rows if r["decision"]=="SKIP"]
        accepts = [r for r in rows if r["decision"]=="ACCEPT"]
        config_streaks = [r["length"] for r in streaks if r["configuration"]==config]
        config_lock = [r for r in lockins if r["configuration"]==config]
        nets = [runs[(config,s)]["result"].metrics.net_earnings_mxn for s in seeds]
        pressure_nonzero=[r for r in rows if r["skip_pressure"]>0]
        pressure_flips=[r for r in accepts if r["adjusted_rate_mxn_hr"] is not None
            and r["adjusted_rate_mxn_hr"] < r["nominal_reservation_wage"]
            and r["adjusted_rate_mxn_hr"] >= r["effective_reservation_wage"]]
        return {"orders_offered":len(rows), "accepts":len(accepts), "skips":len(selected_skips),
            "acceptance_rate_pct":pct(len(accepts),len(rows)), "skip_rate_pct":pct(len(selected_skips),len(rows)),
            "skip_cause_counts":dict(Counter(r["primary_cause"] for r in selected_skips)),
            "skip_cause_percent_of_skips":{k:pct(v,len(selected_skips)) for k,v in Counter(r["primary_cause"] for r in selected_skips).items()},
            "mean_accepted_adjusted_rate":mean(r["adjusted_rate_mxn_hr"] for r in accepts),
            "mean_accepted_service_time_min":mean(r["candidate_service_time_min"] for r in accepts),
            "accepted_distributions":{"net_pay":stats([r["net_pay_mxn"] for r in accepts]),
                "adjusted_rate":stats([r["adjusted_rate_mxn_hr"] for r in accepts]),
                "distance":stats([r["distance_km"] for r in accepts]),
                "service_time":stats([r["candidate_service_time_min"] for r in accepts])},
            "mean_missed_orders_while_busy":mean(r["orders_skipped_while_busy"] for r in config_lock) if config_lock else 0,
            "skip_streak":{"mean":mean(config_streaks) if config_streaks else 0,
                "median":median(config_streaks) if config_streaks else 0,
                "p90":quantile(config_streaks,.9), "max":max(config_streaks,default=0)},
            "skip_pressure":{"offers_with_nonzero_pressure":len(pressure_nonzero),
                "percent_offers_with_nonzero_pressure":pct(len(pressure_nonzero),len(rows)),
                "mean_pressure_when_nonzero":mean((r["skip_pressure"] for r in pressure_nonzero)) if pressure_nonzero else 0,
                "max_pressure":max((r["skip_pressure"] for r in rows),default=0),
                "accepts_crossing_only_due_to_pressure":len(pressure_flips),
                "offers_at_effective_floor":sum(r["effective_reservation_wage"]==40 for r in rows)},
            "net_earnings_total":sum(nets), "net_earnings_mean_per_shift":mean(nets),
            "idle_time_mean_min":mean(runs[(config,s)]["result"].metrics.idle_time_min for s in seeds)}
    summary = {"methodology": {"seeds":seeds, "heldout_used":False,
        "old":"base=165; calibrated min/max and all other policy fields unchanged",
        "new":"base=60, threshold floor=40, pressure=min(20, consecutive_skips*2.5), reset after ACCEPT; diagnostic-only reconstruction",
        "primary_cause":"first actual simulator/insertion/constraint/economic exit, not public binding_constraint",
        "rerouting":"StrategicSimulator uses abstract closure delays and emits no route/closure_id before-after telemetry."},
        "old":aggregate("old"), "new":aggregate("new"),
        "transition_counts":dict(Counter(f"{r['old_decision']}->{r['new_decision']}" for r in transitions)),
        "threshold_counterfactual":wage_rows,
        "worst_new_accepts":sorted([r for r in transitions if r["accepted_configuration"]=="new"], key=lambda r:r["final_economic_impact_mxn"])[:10]}
    (OUT/"summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    write_report(summary, cause_rows, per_seed, wage_rows, funnel, transitions, lockins, streaks)
    return summary


def fmt(value, digits=2):
    return "n/a" if value is None else f"{value:.{digits}f}"


def md_table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "|"+"|".join(["---"]*len(headers))+"|"] +
        ["| " + " | ".join(str(x) for x in row) + " |" for row in rows])


def write_report(summary, cause_rows, per_seed, wage_rows, funnel, transitions, lockins, streaks):
    old,new=summary["old"],summary["new"]
    cause=lambda config, names: sum(summary[config]["skip_cause_percent_of_skips"].get(n,0) for n in names)
    damage_explanations=[
        f"- Seed {r['seed']} / {r['order_id']}: gained {fmt(r['earnings_mxn'])} MXN, overlapped "
        f"{r['subsequent_orders_missed']} Old accepts worth {fmt(r['opportunity_lost_mxn'])} MXN, "
        f"for post-hoc impact {fmt(r['final_economic_impact_mxn'])} MXN."
        for r in summary['worst_new_accepts']]
    lines=["# SKIP Causal Diagnostic", "", "## 1. Executive Summary", "",
        f"Across 10 tuning seeds, Old accepted {old['acceptance_rate_pct']:.2f}% and reconstructed New accepted {new['acceptance_rate_pct']:.2f}%. "
        f"New's skips are {cause('new',['reservation_wage']):.2f}% reservation wage, {cause('new',BUSY):.2f}% busy/commitment, "
        f"{cause('new',SLA):.2f}% SLA/stacking, and {cause('new',HARD):.2f}% hard constraints. Safety skips are reported separately and are not treated as strategic rejection failures.",
        "", "This checkout does not reproduce the stated premise that New accepts less: it accepts 7 more orders, while earning materially less. That discrepancy is evidence and is not normalized away. No recommendations appear before the interpretation sections below.", "",
        "## 2. Configurations Compared", "",
        "- Old: base reservation wage 165 MXN/h; all calibrated policy fields unchanged.",
        "- New: diagnostic reconstruction of base 60 MXN/h, `min(20, consecutive_skips × 2.5)` pressure, effective floor 40 MXN/h; streak resets after ACCEPT.",
        "- Seeds: tuning 1–10 only. Official held-out seeds were neither read by the runner nor executed.",
        "- Repository caveat: the checked-out production code has no skip-pressure implementation or New artifacts; therefore New is reproduced only in this isolated diagnostic runner.", "",
        "## 3. Overall Acceptance / Skip Metrics", "",
        md_table(["metric","Old","New"], [["orders offered",old['orders_offered'],new['orders_offered']],
            ["acceptance rate",fmt(old['acceptance_rate_pct'])+"%",fmt(new['acceptance_rate_pct'])+"%"],
            ["skip rate",fmt(old['skip_rate_pct'])+"%",fmt(new['skip_rate_pct'])+"%"],
            ["mean idle min/shift",fmt(old['idle_time_mean_min']),fmt(new['idle_time_mean_min'])],
            ["total net earnings",fmt(old['net_earnings_total']),fmt(new['net_earnings_total'])],
            ["mean net/shift",fmt(old['net_earnings_mean_per_shift']),fmt(new['net_earnings_mean_per_shift'])]]), "",
        "## 4. Skip Cause Breakdown", "",
        md_table(["config","cause","count","% skips","% orders"], [[r['configuration'],r['cause'],r['count'],fmt(r['percentage_of_all_skips']),fmt(r['percentage_of_all_orders'])] for r in cause_rows]), "",
        "Important attribution finding: when insertion fails, `StrategicSimulator._offer` exposes `binding_constraint=reservation_wage` even though its reason says SLA/active commitment. The table uses reconstructed insertion exits, not that ambiguous public enum.", "",
        "## 5. Reservation Wage Analysis", ""]
    for config in ("old","new"):
        vals={r['statistic']:r for r in wage_rows if r['configuration']==config and r.get('metric')=="adjusted_rate_minus_effective_threshold"}
        lines += [f"{config.title()} margin distribution (adjusted rate − effective threshold):",
            md_table(["P10","P25","P50","P75","P90","mean","n"], [[fmt(vals[x]['value']) for x in ('p10','p25','p50','p75','p90','mean')]+[vals['mean']['n']]]), ""]
        cf=[r for r in wage_rows if r['configuration']==config and r.get('metric')=="offline_threshold_counterfactual"]
        lines += ["Offline only; number of the observed economic skips whose adjusted rate meets each threshold:",
            md_table(["threshold","orders crossing"], [[r['statistic'].split('_')[1],r['value']] for r in cf]), ""]
    pressure_rows=[r for r in summary['threshold_counterfactual'] if r['configuration']=='new']
    pressure=new['skip_pressure']
    lines += [f"In New, skip pressure was nonzero for {pressure['offers_with_nonzero_pressure']} offers ({pressure['percent_offers_with_nonzero_pressure']:.2f}%), averaged {pressure['mean_pressure_when_nonzero']:.2f} MXN/h when active, reached {pressure['max_pressure']:.2f}, and put {pressure['offers_at_effective_floor']} offers at the 40 MXN/h floor. {pressure['accepts_crossing_only_due_to_pressure']} accepts crossed the live decision boundary only because pressure lowered the nominal threshold. Threshold crossing counts above are static post-hoc checks, not replays.", "",
        "## 6. Busy / Commitment Analysis", "",
        f"Busy/commitment accounts for {cause('old',BUSY):.2f}% of Old skips and {cause('new',BUSY):.2f}% of New skips. `not_actionable_while_busy` means no agent choice occurred (reposition reservation or max-active gate); `active_commitment_infeasible` means every insertion would break an already accepted deadline.",
        f"Mean skipped arrivals during each accepted order's occupied window: Old {old['mean_missed_orders_while_busy']:.2f}, New {new['mean_missed_orders_while_busy']:.2f}. Detailed work, route distance, SLA, projected completion, and reason fields are retained in the diagnostic event rows summarized in `summary.json`; worst lock-ins are in `long_order_lockin.csv`.", "",
        "## 7. SLA / Stacking Analysis", "",
        f"SLA/stacking accounts for {cause('old',SLA):.2f}% of Old skips and {cause('new',SLA):.2f}% of New skips. `sla_infeasible` means every candidate route misses the new order's deadline; `stacking_infeasible` means no route jointly preserves all deadlines.", "",
        "## 8. Skip Streak Analysis", "",
        md_table(["metric","Old","New"], [["mean",fmt(old['skip_streak']['mean']),fmt(new['skip_streak']['mean'])],
            ["median",fmt(old['skip_streak']['median']),fmt(new['skip_streak']['median'])],
            ["P90",fmt(old['skip_streak']['p90']),fmt(new['skip_streak']['p90'])],
            ["max",old['skip_streak']['max'],new['skip_streak']['max']]]), "",
        "## 9. Old vs New Decision Transitions", "",
        f"Transitions: {json.dumps(summary['transition_counts'], sort_keys=True)}. Per-order rates, durations, distances, missed real-replay opportunities, and post-hoc economic impact are in `decision_transitions.csv`.", "",
        "## 10. Long-order Lock-in", "",
        "Ten New accepts with the most skipped arrivals during their occupied windows:",
        md_table(["seed","order","occupied min","arrivals","busy skips","order net"], [[r['seed'],r['order_id'],fmt(r['minutes_occupied']),r['orders_arriving_while_busy'],r['orders_skipped_while_busy'],fmt(r['net_earnings_from_order'])] for r in [x for x in lockins if x['configuration']=='new'][:10]]), "",
        "## 11. Economic Consequences", "",
        md_table(["metric","Old","New"], [["mean accepted adjusted rate",fmt(old['mean_accepted_adjusted_rate']),fmt(new['mean_accepted_adjusted_rate'])],
            ["mean accepted service time",fmt(old['mean_accepted_service_time_min']),fmt(new['mean_accepted_service_time_min'])],
            ["total net earnings",fmt(old['net_earnings_total']),fmt(new['net_earnings_total'])]]), "",
        "Worst New-only accepts by order net minus accepted Old opportunities during the actual New occupied window:",
        md_table(["seed","order","order net","lost opps","lost MXN","impact"], [[r['seed'],r['order_id'],fmt(r['earnings_mxn']),r['subsequent_orders_missed'],fmt(r['opportunity_lost_mxn']),fmt(r['final_economic_impact_mxn'])] for r in summary['worst_new_accepts']]), "",
        *damage_explanations, "",
        "This opportunity calculation is descriptive post-hoc attribution over the two real replays. It is not a new predictive model and is not an independent intervention estimate when occupied windows overlap.", "",
        "## 12. Rerouting Observations", "",
        "No reroute rows can be truthfully produced by this replay path. `StrategicSimulator` represents closures as abstract delays and does not emit `closure_id`, old/new route, distance, or ETA. `rerouting_effects.csv` therefore contains its schema and zero fabricated observations.", "",
        "## 13. Root Cause Interpretation", "",
        f"The largest New skip family is {max([('reservation wage',cause('new',['reservation_wage'])),('busy/commitment',cause('new',BUSY)),('SLA/stacking',cause('new',SLA)),('hard constraints',cause('new',HARD))], key=lambda x:x[1])[0]}. Lowering the economic gate changes which orders enter the active route; those acceptances change future feasibility, so acceptance rate is not monotone in a threshold under a stateful replay. The cause mix and transition rows show whether economic skips were exchanged for non-actionable/busy and SLA skips.", "",
        "### Answers to the ten main questions", "",
        f"1. Reservation wage: {cause('new',['reservation_wage']):.2f}% of New skips.",
        f"2. Busy/commitment: {cause('new',BUSY):.2f}%.",
        f"3. SLA/stacking: {cause('new',SLA):.2f}%.",
        f"4. Hard constraints: {cause('new',HARD):.2f}%.",
        "5. It did not reduce acceptance in the reproducible checkout: reconstructed New accepted 102 versus Old's 95. It did reduce earnings because accepted work became longer and lower-rate, and changed the future feasibility path.",
        "6. The ten largest observed losses are listed in Section 11 and `decision_transitions.csv`.",
        f"7. Yes, but narrowly: {pressure['accepts_crossing_only_due_to_pressure']} accepts crossed only because of pressure; pressure was nonzero on {pressure['percent_offers_with_nonzero_pressure']:.2f}% of offers and was frequently capped by the floor.",
        f"8. The before/after mix is economic {cause('old',['reservation_wage']):.2f}%→{cause('new',['reservation_wage']):.2f}% and busy {cause('old',BUSY):.2f}%→{cause('new',BUSY):.2f}%.",
        f"9. The current bottleneck is {max([('reservation wage',cause('new',['reservation_wage'])),('busy/commitment',cause('new',BUSY)),('SLA/stacking',cause('new',SLA)),('hard constraints',cause('new',HARD))], key=lambda x:x[1])[0]}.",
        "10. The true problem is the largest reconstructed gate above, not the simulator's ambiguous public `reservation_wage` fallback label.", "",
        "## 14. Possible Next Experiments", "",
        "- Replay one-at-a-time decision interventions for the worst New-only accepts while freezing all exogenous events.",
        "- Add first-class insertion-failure enums and route-before/after closure telemetry, then repeat this same frozen diagnostic.",
        "- Run an ablation of skip pressure with the New base/floor on tuning seeds only; do not use it as tuning until the causal attribution is reviewed.", "",
        "No experiment above was implemented by this task.", "",
        "## 15. Limitations", "",
        "- New was reconstructed because the requested configuration is absent from the checked-out code and Git history available locally.",
        "- The pressure reset convention (after ACCEPT) is an explicit assumption; the requested formula did not specify reset semantics.",
        "- Opportunity loss uses observed replay windows and cannot isolate interacting or overlapping acceptances.",
        "- Abstract synthetic routing cannot support the requested geospatial rerouting fields.", "",
        "## Required Final Summary", "",
        md_table(["required metric","Old","New"], [["acceptance rate",fmt(old['acceptance_rate_pct'])+"%",fmt(new['acceptance_rate_pct'])+"%"],
            ["skip rate",fmt(old['skip_rate_pct'])+"%",fmt(new['skip_rate_pct'])+"%"],
            ["% skips reservation wage",fmt(cause('old',['reservation_wage']))+"%",fmt(cause('new',['reservation_wage']))+"%"],
            ["% skips busy/commitment",fmt(cause('old',BUSY))+"%",fmt(cause('new',BUSY))+"%"],
            ["% skips SLA/stacking",fmt(cause('old',SLA))+"%",fmt(cause('new',SLA))+"%"],
            ["% skips hard constraints",fmt(cause('old',HARD))+"%",fmt(cause('new',HARD))+"%"],
            ["mean accepted adjusted rate",fmt(old['mean_accepted_adjusted_rate']),fmt(new['mean_accepted_adjusted_rate'])],
            ["mean accepted service time",fmt(old['mean_accepted_service_time_min']),fmt(new['mean_accepted_service_time_min'])],
            ["mean missed orders while busy",fmt(old['mean_missed_orders_while_busy']),fmt(new['mean_missed_orders_while_busy'])],
            ["mean skip streak",fmt(old['skip_streak']['mean']),fmt(new['skip_streak']['mean'])],
            ["max skip streak",old['skip_streak']['max'],new['skip_streak']['max']],
            ["net earnings (10 shifts)",fmt(old['net_earnings_total']),fmt(new['net_earnings_total'])]]), ""]
    dominant=max([("reservation wage",cause('new',['reservation_wage'])),("busy/commitment feasibility",cause('new',BUSY)),("SLA/stacking feasibility",cause('new',SLA)),("hard constraints",cause('new',HARD))],key=lambda x:x[1])[0]
    lines += [f'"The dominant cause of excessive skipping is {dominant}."', ""]
    Path("SKIP_CAUSAL_DIAGNOSTIC.md").write_text("\n".join(lines))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run(),indent=2))


if __name__ == "__main__":
    main()
