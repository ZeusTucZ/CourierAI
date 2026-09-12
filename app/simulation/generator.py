from datetime import timedelta
from random import Random

from app.simulation.config import Range, ScheduledShock, ShiftConfig
from app.simulation.events import Event


def generate_shift(config: ShiftConfig) -> list[Event]:
    rng = Random(config.seed)
    settings = config.simulation
    start = settings.simulation_start_time

    def draw(bounds: Range) -> float:
        return round(rng.uniform(bounds.low, bounds.high), 6)

    events: list[Event] = [{
        "event": "shift_start", "sim_time": start.isoformat(), "seed": config.seed,
        "shift_hours": config.shift_hours, "vehicle": config.vehicle,
        "start_location_zone": config.start_location_zone,
        "shift_end_time": config.shift_end.isoformat(),
    }]
    # First ping at shift start ensures even short positive shifts have an offer.
    at = start
    number = 1
    while at < config.shift_end:
        events.append({
            "event": "order_offered", "order_id": f"ORD-{number:05d}",
            "sim_time": at.isoformat(), "decision_deadline": (at + timedelta(seconds=5)).isoformat(),
            "platform": rng.choice(("rappi", "didi", "uber")),
            "zone_pickup": rng.randint(1, settings.zone_count),
            "zone_dropoff": rng.randint(1, settings.zone_count),
            "distance_pickup_km": draw(settings.distance_pickup_km),
            "distance_delivery_km": draw(settings.distance_delivery_km),
            "base_pay_mxn": draw(settings.base_pay_mxn), "est_tip_mxn": draw(settings.tip_mxn),
            "surge_multiplier": settings.initial_surge_multiplier,
            "restaurant_prep_min": draw(settings.prep_min), "weight_kg": draw(settings.weight_kg),
            "volume_liters": draw(settings.volume_liters), "vehicle": config.vehicle,
        })
        at += timedelta(minutes=draw(settings.order_interval_min))
        number += 1
    schedule = settings.shock_schedule
    if schedule is None:
        schedule = (ScheduledShock(at_min=config.shift_hours * 60 * settings.default_rain_fraction_of_shift,
                                   shock_type="rain", duration_min=settings.default_rain_duration_min),)
    for planned in schedule:
        events.append({"event": "shock", "sim_time": (start + timedelta(minutes=planned.at_min)).isoformat(),
                       **planned.model_dump(mode="json", exclude={"at_min"}, exclude_none=True)})
    events.append({"event": "shift_end", "sim_time": config.shift_end.isoformat()})
    priority = {"shift_start": 0, "shock": 1, "order_offered": 2, "shift_end": 3}
    return sorted(events, key=lambda event: (event["sim_time"], priority[event["event"]]))
