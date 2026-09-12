from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.simulation.config import SyntheticConfig
from app.simulation.events import Shock


@dataclass
class WorldState:
    config: SyntheticConfig
    active: dict[int, Shock] = field(default_factory=dict)
    delays: dict[str, float] = field(default_factory=dict)
    next_id: int = 0

    @property
    def rain_factor(self) -> float:
        return self.config.rain_travel_time_multiplier if any(
            shock.shock_type == "rain" for shock in self.active.values()) else 1.0

    def expire(self, shock_id: int) -> None:
        self.active.pop(shock_id, None)

    def prepare_offer(self, offer: dict, snapshot: StrategySnapshot) -> DecideRequest:
        data = dict(offer)
        data.pop("courier_state_overrides", None)
        order = DecideRequest.model_validate(data)
        profile = snapshot.vehicle_profiles[order.vehicle]
        pickup = order.estimated_pickup_min
        delivery = order.estimated_delivery_min
        updates = {
            "estimated_pickup_min": (pickup if pickup is not None else order.distance_pickup_km / profile.speed_kmh * 60) * self.rain_factor,
            "estimated_delivery_min": (delivery if delivery is not None else order.distance_delivery_km / profile.speed_kmh * 60) * self.rain_factor,
            "restaurant_prep_min": order.restaurant_prep_min + self.delays.get(order.order_id, 0),
        }
        for shock in self.active.values():
            if shock.shock_type == "surge" and shock.zone == order.zone_pickup:
                updates["surge_multiplier"] = shock.multiplier  # Latest active surge wins.
            if shock.shock_type == "closure" and (shock.zone is None or shock.zone in {order.zone_pickup, order.zone_dropoff}):
                updates["restaurant_prep_min"] += self.config.closure_delay_min
        # Round at the simulation's microsecond resolution before the agent sees it.
        for key in ("estimated_pickup_min", "estimated_delivery_min", "restaurant_prep_min"):
            updates[key] = round(updates[key] * 60_000_000) / 60_000_000
        return DecideRequest.model_validate({**order.model_dump(), **updates})


def apply_shock(state: WorldState, shock: Shock) -> tuple[int, datetime | None]:
    """Update exogenous world only. Simulator separately reschedules active work."""
    shock_id = state.next_id
    state.next_id += 1
    if shock.shock_type == "delay":
        state.delays[shock.order_id] = state.delays.get(shock.order_id, 0) + shock.slip_min
        return shock_id, None
    state.active[shock_id] = shock
    return shock_id, shock.sim_time + timedelta(minutes=shock.duration_min)
