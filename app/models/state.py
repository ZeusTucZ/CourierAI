from datetime import datetime, timedelta

from pydantic import Field

from app.models.common import Model, NonNegative


class InFlightOrder(Model):
    """MVP adapter: all time/distance fields describe REMAINING work.

    The official files specify the array but not its item schema.
    Missing load/timing is retained as unknown, never treated as empty work.
    """

    order_id: str
    weight_kg: NonNegative | None = None
    volume_liters: NonNegative | None = None
    distance_pickup_km: NonNegative | None = None
    distance_delivery_km: NonNegative | None = None
    estimated_pickup_min: NonNegative | None = None
    estimated_delivery_min: NonNegative | None = None
    restaurant_prep_min: NonNegative = 0
    zone_dropoff: int | None = Field(default=None, strict=True)


class CourierStateOverrides(Model):
    continuous_riding_min: NonNegative | None = None
    shift_elapsed_hours: NonNegative | None = None
    last_break_end_time: datetime | None = None
    shift_end_time: datetime | None = None
    in_flight_orders: tuple[InFlightOrder, ...] | None = None


class CourierState(Model):
    continuous_riding_min: NonNegative
    shift_elapsed_hours: NonNegative
    last_break_end_time: datetime | None = None
    shift_end_time: datetime
    in_flight_orders: tuple[InFlightOrder, ...] = ()


def resolve_state(sim_time: datetime, overrides: CourierStateOverrides | None,
                  default_shift_hours: float) -> CourierState:
    """Request-local state; accepting an offer never advances a simulated shift."""
    override = overrides or CourierStateOverrides()
    elapsed = override.shift_elapsed_hours or 0.0
    shift_end = override.shift_end_time or (
        sim_time + timedelta(hours=default_shift_hours - elapsed)
    )
    continuous = override.continuous_riding_min
    if continuous is None:
        # Conservative when only elapsed time is supplied; do not infer a break.
        continuous = elapsed * 60
        if override.last_break_end_time is not None:
            continuous = max(0.0, (sim_time - override.last_break_end_time).total_seconds() / 60)
    return CourierState(
        continuous_riding_min=continuous, shift_elapsed_hours=elapsed,
        last_break_end_time=override.last_break_end_time, shift_end_time=shift_end,
        in_flight_orders=override.in_flight_orders or (),
    )
