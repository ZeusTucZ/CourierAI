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


@dataclass
class RouteStep:
    order_id: str
    phase: object
    zone: int


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


def insert_order(route, job, jobs, request, snapshot, policy, *, improved=True):
    if len(jobs) >= policy.max_active_orders:
        return None
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
    for sequence in candidates:
        plan, completion = route_plan(sequence, request.sim_time, job.offer.order_id)
        if any(completion[key] > deadline for key, deadline in deadlines.items()):
            continue
        if evaluate_constraints(request, state, snapshot, plan) is not None:
            continue
        # Minimize sum of completion times; stable candidate order breaks ties.
        score = sum((when - request.sim_time).total_seconds() for when in completion.values())
        feasible.append((score, sequence, plan))
    if not feasible:
        return None
    _, sequence, plan = min(feasible, key=lambda item: item[0])
    return sequence, plan
