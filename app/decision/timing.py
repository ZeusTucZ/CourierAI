from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config.vehicles import VehicleProfile
from app.models.requests import DecideRequest
from app.models.state import CourierState, InFlightOrder
from app.models.strategy import StrategySnapshot


@dataclass(frozen=True)
class WorkPlan:
    total_time_min: float
    new_order_time_min: float
    riding_min: float
    completion_time: datetime
    riding_intervals: tuple[tuple[datetime, datetime], ...]
    dropoffs: tuple[tuple[int | None, datetime], ...]
    unknown_timing: bool


def leg_minutes(estimate: float | None, distance: float | None,
                profile: VehicleProfile) -> float | None:
    if estimate is not None:
        return estimate
    return None if distance is None else distance / profile.speed_kmh * 60


def build_work_plan(order: DecideRequest, state: CourierState,
                    snapshot: StrategySnapshot) -> WorkPlan:
    """Finish existing work serially, then the new order; no route sharing.

    Preparation is waiting, never credited as a verified mandatory break.
    """
    profile = snapshot.vehicle_profiles[order.vehicle]
    cursor = order.sim_time
    intervals = []
    dropoffs = []
    riding = 0.0
    total = 0.0
    new_time = 0.0
    unknown = False
    work: tuple[InFlightOrder | DecideRequest, ...] = (*state.in_flight_orders, order)
    for item in work:
        if isinstance(item, InFlightOrder) and item.minutes_remaining is not None:
            service = max(item.minutes_remaining, snapshot.policy.minimum_service_time_min)
            end = cursor + timedelta(minutes=service)
            # The runner only supplies a remaining duration, not the phase
            # split. Conservatively treat it as riding for time safeguards.
            intervals.append((cursor, end))
            riding += service
            cursor = end
            total += service
            dropoffs.append((item.zone_dropoff, cursor))
            continue
        pickup = leg_minutes(item.estimated_pickup_min, item.distance_pickup_km, profile)
        delivery = leg_minutes(item.estimated_delivery_min, item.distance_delivery_km, profile)
        if pickup is None or delivery is None:
            unknown = True
            continue
        service = max(pickup + item.restaurant_prep_min + delivery,
                      snapshot.policy.minimum_service_time_min)
        if item is order:
            new_time = service
        for duration, is_riding in ((pickup, True), (item.restaurant_prep_min, False),
                                    (delivery, True),
                                    (service - pickup - delivery - item.restaurant_prep_min, False)):
            end = cursor + timedelta(minutes=max(0, duration))
            if is_riding and duration > 0:
                intervals.append((cursor, end))
                riding += duration
            cursor = end
        total += service
        dropoffs.append((item.zone_dropoff, cursor))
    return WorkPlan(total, new_time, riding, cursor, tuple(intervals), tuple(dropoffs), unknown)
