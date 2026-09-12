from datetime import datetime, timedelta

from app.agents.smart import SmartAgent
from app.models.strategy import StrategySnapshot
from app.simulation.config import ShiftConfig, SyntheticConfig
from app.simulation.events import event_time
from app.simulation.simulator import Simulator


def config(start="2026-03-21T18:00:00", hours=1, vehicle="moto", **settings):
    return ShiftConfig(seed=42, shift_hours=hours, vehicle=vehicle, start_location_zone=7,
                       simulation=SyntheticConfig(simulation_start_time=datetime.fromisoformat(start),
                                                  shock_schedule=(), **settings))


def offer(cfg, at=0, order_id="ONE", **changes):
    when = cfg.simulation.simulation_start_time + timedelta(minutes=at)
    return {"event": "order_offered", "order_id": order_id, "sim_time": when.isoformat(),
            "zone_pickup": 7, "zone_dropoff": 7, "distance_pickup_km": 1,
            "distance_delivery_km": 2, "base_pay_mxn": 1000, "est_tip_mxn": 10,
            "surge_multiplier": 1, "restaurant_prep_min": 0, "weight_kg": 1,
            "volume_liters": 2, "vehicle": cfg.vehicle, "estimated_pickup_min": 5,
            "estimated_delivery_min": 5, **changes}


def shock(cfg, at, kind, **fields):
    return {"event": "shock", "sim_time": (cfg.simulation.simulation_start_time + timedelta(minutes=at)).isoformat(),
            "shock_type": kind, **fields}


def stream(cfg, *events):
    start = {"event": "shift_start", "sim_time": cfg.simulation.simulation_start_time.isoformat(),
             "seed": cfg.seed, "shift_hours": cfg.shift_hours, "vehicle": cfg.vehicle,
             "start_location_zone": cfg.start_location_zone, "shift_end_time": cfg.shift_end.isoformat()}
    priority = {"shock": 0, "order_offered": 1}
    return [start, *sorted(events, key=lambda e: (event_time(e), priority[e["event"]])),
            {"event": "shift_end", "sim_time": cfg.shift_end.isoformat()}]


def run(cfg, *events, agent=None):
    return Simulator(cfg, agent or SmartAgent(StrategySnapshot())).run(stream(cfg, *events))


def selected(result, event_type):
    return [event for event in result.log.events if event["event"] == event_type]


# Named builders shared by the controlled audit scenarios and console demos.
def make_shift(**changes):
    return config(**changes)


def make_order(cfg, **changes):
    return offer(cfg, **changes)


def make_state(cfg):
    from app.simulation.state import CourierState
    return CourierState.for_shift(cfg)


def make_shock(cfg, at, kind, **fields):
    return shock(cfg, at, kind, **fields)
