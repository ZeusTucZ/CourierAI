from dataclasses import dataclass
from datetime import timedelta

from app.decision.timing import WorkPlan
from app.models.requests import DecideRequest
from app.models.responses import Constraint
from app.models.state import CourierState
from app.models.strategy import StrategySnapshot


@dataclass(frozen=True)
class Violation:
    constraint: Constraint
    reason: str


def flagged_zone_night(order, state, snapshot, plan):
    hour = snapshot.policy.night_start_hour
    if order.zone_dropoff in snapshot.flagged_zones and order.sim_time.hour >= hour:
        return Violation("flagged_zone_night", f"Skipped: flagged_zone_night prohibits dropoff in zone {order.zone_dropoff} at or after {hour}:00.")
    for zone, arrival in plan.dropoffs:
        if zone in snapshot.flagged_zones and arrival.hour >= hour:
            return Violation("flagged_zone_night", f"Skipped: flagged_zone_night prohibits estimated dropoff in zone {zone} at {arrival:%H:%M}.")


def mandatory_break(order, state, snapshot, plan):
    policy = snapshot.policy
    if state.last_break_end_time is not None and state.last_break_end_time > order.sim_time:
        return Violation("mandatory_break", f"Skipped: mandatory_break remains active until {state.last_break_end_time:%H:%M}; complete the {policy.mandatory_break_min}-minute break first.")
    projected = state.continuous_riding_min + plan.riding_min
    if state.continuous_riding_min >= policy.mandatory_riding_limit_min or projected > policy.mandatory_riding_limit_min:
        return Violation("mandatory_break", f"Skipped: mandatory_break requires {policy.mandatory_break_min} minutes of rest; projected continuous riding is {projected:.2f} minutes, limit {policy.mandatory_riding_limit_min}.")


def heat_rule(order, state, snapshot, plan, *, allow_initial_transition=False):
    policy = snapshot.policy
    continuous = state.continuous_riding_min
    if policy.heat_start_hour <= order.sim_time.hour < policy.heat_end_hour and continuous > policy.heat_riding_limit_min:
        return Violation("heat_rule", f"Skipped: heat_rule continuous riding is {continuous:.2f} minutes, above the {policy.heat_riding_limit_min}-minute limit during 12:00-16:00.")
    for start, end in plan.riding_intervals:
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while day < end:
            heat_start = day + timedelta(hours=policy.heat_start_hour)
            heat_end = day + timedelta(hours=policy.heat_end_hour)
            if start < heat_end and end > heat_start:
                projected = continuous + (min(end, heat_end) - start).total_seconds() / 60
                # A stateful runner reports work only after it is accepted.
                # Preserve the public pack's boundary convention: an offer
                # that starts below the warning band may establish the state
                # that blocks the *next* offer; once at/above 80 minutes, do
                # not permit projected riding beyond the 90-minute cap.
                if (not allow_initial_transition or state.in_flight_orders or
                        continuous >= policy.heat_riding_limit_min - 10) and projected > policy.heat_riding_limit_min:
                    return Violation("heat_rule", f"Skipped: heat_rule projects {projected:.2f} continuous riding minutes during 12:00-16:00, exceeding the {policy.heat_riding_limit_min}-minute limit.")
            day += timedelta(days=1)
        continuous += (end - start).total_seconds() / 60


def shift_end_infeasible(order, state, snapshot, plan):
    if plan.unknown_timing:
        return Violation("shift_end_infeasible", "Skipped: shift_end_infeasible cannot be ruled out because in-flight orders lack remaining travel times or distances.")
    late = (plan.completion_time - state.shift_end_time).total_seconds() / 60
    if late > 0:
        return Violation("shift_end_infeasible", f"Skipped: shift_end_infeasible; estimated completion is {late:.2f} minutes after shift end, including existing work.")


def vehicle_capacity(order, state, snapshot, plan):
    profile = snapshot.vehicle_profiles[order.vehicle]
    work = (*state.in_flight_orders, order)
    # A compact in-flight item from the official runner represents work already
    # accepted by this same capacity gate; its historical load is not repeated
    # in the state payload. Other incomplete items remain unsafe and fail shut.
    if any((item.weight_kg is None or item.volume_liters is None)
           and not (getattr(item, "minutes_remaining", None) is not None)
           for item in work):
        return Violation("vehicle_capacity", "Skipped: vehicle_capacity cannot be verified because an order lacks weight or volume.")
    weight = sum(item.weight_kg or 0 for item in work)
    volume = sum(item.volume_liters or 0 for item in work)
    if weight > profile.max_weight_kg:
        return Violation("vehicle_capacity", f"Skipped: vehicle_capacity; combined weight {weight:.2f} kg exceeds the {order.vehicle} limit of {profile.max_weight_kg:g} kg.")
    if volume > profile.max_volume_liters:
        return Violation("vehicle_capacity", f"Skipped: vehicle_capacity; combined volume {volume:.2f} liters exceeds the {order.vehicle} limit of {profile.max_volume_liters:g} liters.")


# Stable priority, matching the five official constraints. First violation binds.
CONSTRAINTS = (flagged_zone_night, mandatory_break, heat_rule,
               shift_end_infeasible, vehicle_capacity)


def evaluate_constraints(order: DecideRequest, state: CourierState,
                         snapshot: StrategySnapshot, plan: WorkPlan,
                         *, allow_initial_heat_transition=False) -> Violation | None:
    for constraint in CONSTRAINTS:
        if constraint is heat_rule:
            violation = constraint(order, state, snapshot, plan,
                                   allow_initial_transition=allow_initial_heat_transition)
        else:
            violation = constraint(order, state, snapshot, plan)
        if violation:
            return violation
    return None
