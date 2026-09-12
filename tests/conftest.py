from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.decision.engine import DecisionEngine
from app.main import create_app
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot


@pytest.fixture
def payload():
    return {
        "order_id": "TEST-001", "platform": "rappi", "sim_time": "2026-03-21T18:00:00",
        "zone_pickup": 7, "zone_dropoff": 7, "distance_pickup_km": 1,
        "distance_delivery_km": 2, "base_pay_mxn": 100, "est_tip_mxn": 10,
        "surge_multiplier": 1, "restaurant_prep_min": 0,
        "weight_kg": 1, "volume_liters": 2, "vehicle": "moto",
        "estimated_pickup_min": 5, "estimated_delivery_min": 5,
        "courier_state_overrides": {"shift_end_time": "2026-03-21T23:00:00",
                                    "continuous_riding_min": 0},
    }


@pytest.fixture
def snapshot():
    return StrategySnapshot()


@pytest.fixture
def evaluate(payload, snapshot):
    def run(changes=None, strategy=None):
        data = deepcopy(payload)
        data.update(changes or {})
        return DecisionEngine().evaluate(DecideRequest.model_validate(data), strategy or snapshot).response
    return run


@pytest.fixture
def client():
    with TestClient(create_app()) as instance:
        yield instance
