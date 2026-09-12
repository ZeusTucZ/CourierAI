from datetime import timedelta
from random import Random

from app.simulation.config import Range, ScheduledShock, ShiftConfig
from app.simulation.events import Event


def generate_shift(config: ShiftConfig) -> list[Event]:
    rng = Random(config.seed)
    settings = config.simulation
    profile = config.profile
    start = settings.simulation_start_time

    def draw(bounds: Range) -> float:
        return round(rng.uniform(bounds.low, bounds.high), 6)

    def value(bounds, name):
        return getattr(profile, name).sample(rng) if profile else draw(bounds)

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
        if profile and profile.time_of_day_demand_profile[at.hour] == 0:
            at = at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            continue
        transition = rng.choices(profile.zone_transition_distribution,
            weights=[t.count for t in profile.zone_transition_distribution])[0] if profile and profile.zone_transition_distribution else None
        events.append({
            "event": "order_offered", "order_id": f"ORD-{number:05d}",
            "sim_time": at.isoformat(), "decision_deadline": (at + timedelta(seconds=5)).isoformat(),
            "platform": rng.choice(("rappi", "didi", "uber")),
            "zone_pickup": transition.pickup if transition else rng.randint(1, settings.zone_count),
            "zone_dropoff": transition.dropoff if transition else rng.randint(1, settings.zone_count),
            "distance_pickup_km": value(settings.distance_pickup_km, "pickup_distance_distribution"),
            "distance_delivery_km": value(settings.distance_delivery_km, "order_distance_distribution"),
            "base_pay_mxn": value(settings.base_pay_mxn, "base_pay_distribution"), "est_tip_mxn": value(settings.tip_mxn, "tip_distribution"),
            "surge_multiplier": settings.initial_surge_multiplier,
            "restaurant_prep_min": value(settings.prep_min, "prep_time_distribution"), "weight_kg": value(settings.weight_kg, "weight_distribution"),
            "volume_liters": value(settings.volume_liters, "volume_distribution"), "vehicle": config.vehicle,
        })
        interval = max(.000001, rng.expovariate(profile.orders_per_hour * profile.time_of_day_demand_profile[at.hour] / 60)) if profile else draw(settings.order_interval_min)
        at += timedelta(minutes=interval)
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
