"""Bounded pickup/delivery insertion over remaining phases; no solver dependency.

    Durations/distances are quoted synthetic legs, not geographic shortest paths.
    The current phase is never preempted; new pickup+prep and delivery are inserted
    in separate positions without changing the relative order of existing phases.
"""
from dataclasses import dataclass
from datetime import timedelta

from app.decision.timing import WorkPlan
from app.decision.constraints import evaluate_constraints
from app.models.state import resolve_state
from app.simulation.state import MINUTE_US
from app.strategy.smart_v2 import sla_risk_penalty


@dataclass
class RouteStep:
    order_id: str
    phase: object
    zone: int


@dataclass(frozen=True)
class InsertionDiagnostics:
    candidate: tuple[list[RouteStep], WorkPlan] | None
    decision_cause: str | None
    candidates_considered: int
    deadline_rejections: int
    constraint_rejections: int
    best_rejected_sla_margin_min: float | None


def steps_for(job):
    return [RouteStep(job.offer.order_id, phase, job.offer.zone_pickup if phase.kind in ("to_pickup", "waiting") else job.offer.zone_dropoff)
            for phase in job.phases]


def route_plan(route, now, new_id=None):
    cursor, riding, new_time = now, 0, 0
    intervals, dropoffs, completions = [], [], {}
    for step in route:
        duration = step.phase.remaining_us / MINUTE_US
        end = cursor + timedelta(microseconds=step.phase.remaining_us)
        if step.phase.kind != "waiting" and duration:
            intervals.append((cursor, end))
            riding += duration
        if step.order_id == new_id:
            new_time += duration
        if step.phase.kind == "to_dropoff":
            dropoffs.append((step.zone, end))
        completions[step.order_id] = end
        cursor = end
    return WorkPlan((cursor - now).total_seconds() / 60, new_time, riding, cursor,
                    tuple(intervals), tuple(dropoffs), False), completions


def inspect_insert_order(route, job, jobs, request, snapshot, policy, *, improved=True):
    if len(jobs) >= policy.max_active_orders:
        return InsertionDiagnostics(None, "capacity", 0, 0, 1, None)
    new = steps_for(job)
    candidates = [route + new]
    if improved:
        # Avoid splitting pickup from restaurant wait and avoid preempting travel.
        for pickup in range(1 if route else 0, len(route) + 1):
            for delivery in range(pickup, len(route) + 1):
                if len(candidates) >= policy.max_insertions:
                    break
                candidates.append(route[:pickup] + new[:2] + route[pickup:delivery] + new[2:] + route[delivery:])
            if len(candidates) >= policy.max_insertions:
                break
    state = resolve_state(request.sim_time, request.courier_state_overrides, snapshot.policy.default_shift_hours)
    deadlines = {j.offer.order_id: j.promised_completion_time for j in (*jobs, job)}
    feasible = []
    deadline_rejections = 0
    constraint_rejections = 0
    rejected_margins = []
    for sequence in candidates:
        plan, completion = route_plan(sequence, request.sim_time, job.offer.order_id)
        margins = [(deadline - completion[key]).total_seconds() / 60
                   for key, deadline in deadlines.items()]
        if min(margins) < 0:
            deadline_rejections += 1
            rejected_margins.append(min(margins))
            continue
        if evaluate_constraints(request, state, snapshot, plan) is not None:
            constraint_rejections += 1
            continue
        # Minimize sum of completion times; stable candidate order breaks ties.
        completion_sum = sum((when - request.sim_time).total_seconds() for when in completion.values())
        if policy.use_smart_v2_scoring and jobs:
            current_plan, _ = route_plan(route, request.sim_time)
            incremental_time = max(0.0, plan.total_time_min - current_plan.total_time_min)
            incremental_distance = max(0.0,
                sum(step.phase.distance_km for step in sequence) -
                sum(step.phase.distance_km for step in route))
            operating_cost = incremental_distance * snapshot.vehicle_profiles[request.vehicle].operating_cost_mxn_per_km
            risk = sla_risk_penalty(min(margins), policy.preferred_sla_buffer_min,
                                    policy.sla_risk_cost_per_min)
            score = (operating_cost + snapshot.reservation_wage_mxn_hr * incremental_time / 60 + risk,
                     completion_sum)
        else:
            score = (completion_sum,)
        feasible.append((score, sequence, plan))
    if not feasible:
        cause = "sla_infeasible" if deadline_rejections else "hard_constraint"
        return InsertionDiagnostics(None, cause, len(candidates), deadline_rejections,
                                    constraint_rejections,
                                    max(rejected_margins) if rejected_margins else None)
    _, sequence, plan = min(feasible, key=lambda item: item[0])
    return InsertionDiagnostics((sequence, plan), None, len(candidates),
                                deadline_rejections, constraint_rejections, None)


def insert_order(route, job, jobs, request, snapshot, policy, *, improved=True):
    """Compatibility wrapper retaining the existing insertion API."""
    return inspect_insert_order(route, job, jobs, request, snapshot, policy,
                                improved=improved).candidate
