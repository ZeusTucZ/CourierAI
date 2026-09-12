from hashlib import sha256
from random import Random

import pytest
from pydantic import ValidationError

from app.logging.event_log import encode_events
from app.simulation.config import ScheduledShock, ShiftConfig, SyntheticConfig
from app.simulation.events import event_time
from app.simulation.generator import generate_shift


@pytest.mark.parametrize("vehicle", ["moto", "car", "bike"])
def test_same_config_byte_identical(vehicle):
    config = ShiftConfig(seed=1234, shift_hours=8, vehicle=vehicle, start_location_zone=7)
    first = encode_events(generate_shift(config))
    Random(999).random()  # Unrelated randomness cannot influence the generator.
    assert first == encode_events(generate_shift(config))
    assert sha256(first).hexdigest() == sha256(encode_events(generate_shift(config))).hexdigest()


def test_different_seed_changes_stream():
    config = ShiftConfig(seed=1, shift_hours=1, vehicle="moto", start_location_zone=7)
    assert encode_events(generate_shift(config)) != encode_events(generate_shift(config.model_copy(update={"seed": 2})))


def test_generator_covers_fields_and_chronology():
    cfg = ShiftConfig(seed=3, shift_hours=8, vehicle="car", start_location_zone=7)
    events = generate_shift(cfg)
    assert [event_time(e) for e in events] == sorted(event_time(e) for e in events)
    assert {e["event"] for e in events} == {"shift_start", "shift_end", "shock", "order_offered"}
    offers = [e for e in events if e["event"] == "order_offered"]
    assert len({e["order_id"] for e in offers}) == len(offers)
    for offer in offers:
        assert offer.keys() >= {"event", "order_id", "sim_time", "zone_pickup", "zone_dropoff",
                               "distance_pickup_km", "distance_delivery_km", "base_pay_mxn",
                               "surge_multiplier", "vehicle", "weight_kg", "volume_liters"}


@pytest.mark.parametrize("change", [{"shift_hours": 0}, {"shift_hours": -1}, {"vehicle": "truck"},
                                   {"start_location_zone": 99}, {"seed": True}])
def test_invalid_shift_config(change):
    with pytest.raises(ValidationError):
        ShiftConfig.model_validate({"seed": 1, "shift_hours": 8, "vehicle": "moto", "start_location_zone": 7, **change})


@pytest.mark.parametrize("settings", [{"order_interval_min": {"low": 0, "high": 1}},
    {"base_pay_mxn": {"low": 10, "high": 1}}, {"rain_travel_time_multiplier": .9}])
def test_invalid_synthetic_settings(settings):
    with pytest.raises(ValidationError):
        SyntheticConfig.model_validate(settings)


@pytest.mark.parametrize("kind,fields", [("surge", {"zone": 7, "multiplier": 2, "duration_min": 5}),
    ("closure", {"zone": 7, "duration_min": 5}), ("rain", {"duration_min": 5}),
    ("delay", {"order_id": "ORD-00001", "slip_min": 3})])
def test_explicit_shock_schedule(kind, fields):
    cfg = ShiftConfig(seed=4, shift_hours=1, vehicle="bike", start_location_zone=7,
        simulation=SyntheticConfig(shock_schedule=(ScheduledShock(at_min=5, shock_type=kind, **fields),)))
    shocks = [e for e in generate_shift(cfg) if e["event"] == "shock"]
    assert len(shocks) == 1 and shocks[0]["shock_type"] == kind
