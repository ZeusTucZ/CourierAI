from dataclasses import dataclass
from math import hypot


def zone_distance(a, b, spacing):
    """Explicit synthetic grid of 4 columns; zone IDs are not real geography."""
    return hypot((a - 1) % 4 - (b - 1) % 4, (a - 1) // 4 - (b - 1) // 4) * spacing


@dataclass(frozen=True)
class RepositionAction:
    zone: int
    distance_km: float
    travel_min: float
    operating_cost_mxn: float
    gain_mxn: float


def choose_reposition(state, snapshot, policy, last_move=None, rain_factor=1):
    if not policy.use_reposition or state.in_flight_orders or state.break_until:
        return None
    if last_move is not None and (state.current_sim_time - last_move).total_seconds() / 60 < policy.minimum_dwell_time_min:
        return None
    profile = snapshot.vehicle_profiles[state.vehicle]
    current = snapshot.zone_predictions.get(state.current_zone)
    wait_rate = (current.expected_net_mxn_per_hour or 0) if current else 0
    remaining = (state.shift_end - state.current_sim_time).total_seconds() / 60
    horizon = min(policy.reposition_horizon_min, remaining)
    candidates = []
    for zone, prediction in sorted(snapshot.zone_predictions.items()):
        if zone == state.current_zone:
            continue
        distance = zone_distance(state.current_zone, zone, policy.synthetic_zone_spacing_km)
        travel = distance / profile.speed_kmh * 60 * rain_factor
        cost = distance * profile.operating_cost_mxn_per_km
        gain = (prediction.expected_net_mxn_per_hour or 0) * max(0, horizon - travel) / 60 - wait_rate * horizon / 60 - cost
        if travel <= remaining and gain > policy.minimum_reposition_gain:
            candidates.append(RepositionAction(zone, distance, travel, cost, gain))
    return max(candidates, key=lambda action: (action.gain_mxn, -action.zone)) if candidates else None
