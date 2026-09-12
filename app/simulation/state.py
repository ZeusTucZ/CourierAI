from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from app.models.requests import DecideRequest
from app.models.state import CourierStateOverrides, InFlightOrder
from app.models.strategy import StrategySnapshot
from app.simulation.config import ShiftConfig

MINUTE_US = 60_000_000


def to_us(minutes: float) -> int:
    return round(minutes * MINUTE_US)


@dataclass
class Phase:
    kind: Literal["to_pickup", "waiting", "to_dropoff"]
    remaining_us: int
    distance_km: float = 0


@dataclass
class ActiveOrder:
    offer: DecideRequest
    phases: list[Phase]
    promised_completion_time: datetime
    estimated_completion_time: datetime

    @classmethod
    def accepted(cls, offer: DecideRequest, snapshot: StrategySnapshot, completion: datetime):
        profile = snapshot.vehicle_profiles[offer.vehicle]
        pickup = offer.estimated_pickup_min
        delivery = offer.estimated_delivery_min
        if pickup is None:
            pickup = offer.distance_pickup_km / profile.speed_kmh * 60
        if delivery is None:
            delivery = offer.distance_delivery_km / profile.speed_kmh * 60
        padding = max(0, snapshot.policy.minimum_service_time_min - pickup - delivery - offer.restaurant_prep_min)
        phases = [Phase("to_pickup", to_us(pickup), offer.distance_pickup_km),
                  Phase("waiting", to_us(offer.restaurant_prep_min)),
                  Phase("to_dropoff", to_us(delivery), offer.distance_delivery_km),
                  Phase("waiting", to_us(padding))]
        return cls(offer, phases, completion, completion)

    def remaining(self) -> InFlightOrder:
        return InFlightOrder(
            order_id=self.offer.order_id, weight_kg=self.offer.weight_kg,
            volume_liters=self.offer.volume_liters, zone_dropoff=self.offer.zone_dropoff,
            estimated_pickup_min=sum(p.remaining_us for p in self.phases if p.kind == "to_pickup") / MINUTE_US,
            estimated_delivery_min=sum(p.remaining_us for p in self.phases if p.kind == "to_dropoff") / MINUTE_US,
            restaurant_prep_min=sum(p.remaining_us for p in self.phases if p.kind == "waiting") / MINUTE_US,
            distance_pickup_km=sum(p.distance_km for p in self.phases if p.kind == "to_pickup"),
            distance_delivery_km=sum(p.distance_km for p in self.phases if p.kind == "to_dropoff"),
        )

    def add_delay(self, minutes: float) -> None:
        # Restaurant delay goes after remaining pickup, before delivery.
        # For an order already travelling to dropoff, wait before resuming.
        index = 1 if self.phases and self.phases[0].kind == "to_pickup" else 0
        self.phases.insert(index, Phase("waiting", to_us(minutes)))


@dataclass
class CourierState:
    current_sim_time: datetime
    current_zone: int
    status: str
    vehicle: str
    shift_start: datetime
    shift_end: datetime
    continuous_riding_us: int = 0
    last_break_end_time: datetime | None = None
    break_until: datetime | None = None
    in_flight_orders: list[ActiveOrder] = field(default_factory=list)
    gross_earnings: float = 0
    operating_costs: float = 0
    distance_traveled_km: float = 0
    idle_time_us: int = 0
    orders_offered: int = 0
    orders_accepted: int = 0
    orders_skipped: int = 0
    orders_completed: int = 0
    late_deliveries: int = 0
    safety_violations: int = 0
    execution_hold: str | None = None
    post_accept_infeasible: int = 0
    skip_penalties: float = 0
    cancellation_penalties: float = 0
    orders_cancelled: int = 0
    reposition_count: int = 0
    reposition_distance_km: float = 0
    reposition_cost_mxn: float = 0
    disruption_caused_lateness: int = 0

    @classmethod
    def for_shift(cls, config: ShiftConfig):
        return cls(config.simulation.simulation_start_time, config.start_location_zone,
                   "idle", config.vehicle, config.simulation.simulation_start_time, config.shift_end)

    @property
    def continuous_riding_min(self):
        return self.continuous_riding_us / MINUTE_US

    @property
    def current_weight_kg(self):
        return sum(job.offer.weight_kg or 0 for job in self.in_flight_orders)

    @property
    def current_volume_liters(self):
        return sum(job.offer.volume_liters or 0 for job in self.in_flight_orders)

    @property
    def net_earnings(self):
        return self.gross_earnings - self.operating_costs - self.skip_penalties - self.cancellation_penalties

    @property
    def idle_time_min(self):
        return self.idle_time_us / MINUTE_US

    def overrides(self) -> CourierStateOverrides:
        return CourierStateOverrides(
            continuous_riding_min=self.continuous_riding_min,
            shift_elapsed_hours=(self.current_sim_time - self.shift_start).total_seconds() / 3600,
            # MVP 1 represents an active break by its scheduled end in this field.
            last_break_end_time=self.break_until or self.last_break_end_time,
            shift_end_time=self.shift_end,
            in_flight_orders=tuple(job.remaining() for job in self.in_flight_orders),
        )

    def recompute_completions(self) -> None:
        cursor = self.current_sim_time
        for job in self.in_flight_orders:
            cursor += timedelta(microseconds=sum(p.remaining_us for p in job.phases))
            job.estimated_completion_time = cursor

    def summary(self) -> dict:
        return {
            "current_sim_time": self.current_sim_time.isoformat(), "current_zone": self.current_zone,
            "status": self.status, "vehicle": self.vehicle,
            "shift_start": self.shift_start.isoformat(), "shift_end": self.shift_end.isoformat(),
            **self.overrides().model_dump(mode="json"),
            "current_weight_kg": self.current_weight_kg, "current_volume_liters": self.current_volume_liters,
            "gross_earnings": self.gross_earnings, "operating_costs": self.operating_costs,
            "net_earnings": self.net_earnings, "distance_traveled_km": self.distance_traveled_km,
            "idle_time_min": self.idle_time_min, "orders_offered": self.orders_offered,
            "orders_accepted": self.orders_accepted, "orders_skipped": self.orders_skipped,
            "orders_completed": self.orders_completed, "late_deliveries": self.late_deliveries,
            "safety_violations": self.safety_violations, "execution_hold": self.execution_hold,
            "post_accept_infeasible": self.post_accept_infeasible,
        }
