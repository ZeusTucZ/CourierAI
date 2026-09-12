from pathlib import Path
from random import Random
from typing import Literal

from pydantic import Field, model_validator

from app.models.common import Model, NonNegative, Positive


class Distribution(Model):
    kind: Literal["uniform", "empirical"] = "uniform"
    low: NonNegative = 0
    high: NonNegative = 1
    values: tuple[NonNegative, ...] = ()

    @model_validator(mode="after")
    def valid(self):
        if self.high < self.low or (self.kind == "empirical" and not self.values):
            raise ValueError("Invalid distribution bounds or empty empirical sample")
        return self

    def sample(self, rng: Random) -> float:
        return round(rng.choice(self.values) if self.kind == "empirical" else rng.uniform(self.low, self.high), 6)


class Transition(Model):
    pickup: int = Field(ge=1)
    dropoff: int = Field(ge=1)
    count: int = Field(gt=0)


class Provenance(Model):
    parameter: str
    source: str
    classification: Literal["observed", "derived", "assumed", "synthetic", "official"]
    sample_size: int = Field(ge=0)
    transformation: str
    fallback: str | None = None


class SimulationProfile(Model):
    kind: Literal["synthetic", "calibrated"] = "synthetic"
    name: str = "synthetic-v1"
    orders_per_hour: Positive = 15
    pickup_distance_distribution: Distribution = Distribution(low=.3, high=3)
    order_distance_distribution: Distribution = Distribution(low=.5, high=6)
    prep_time_distribution: Distribution = Distribution(low=0, high=8)
    service_time_distribution: Distribution | None = None
    base_pay_distribution: Distribution = Distribution(low=35, high=120)
    tip_distribution: Distribution = Distribution(low=0, high=20)
    weight_distribution: Distribution = Distribution(low=.5, high=6)
    volume_distribution: Distribution = Distribution(low=1, high=12)
    zone_transition_distribution: tuple[Transition, ...] = ()
    time_of_day_demand_profile: tuple[NonNegative, ...] = (1,) * 24
    provenance: tuple[Provenance, ...] = ()
    training_seeds: tuple[int, ...] = ()
    source_sha256: str | None = None

    @model_validator(mode="after")
    def hours(self):
        if len(self.time_of_day_demand_profile) != 24:
            raise ValueError("Exactly 24 demand factors required")
        return self

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path):
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


class SyntheticProfile(SimulationProfile):
    kind: Literal["synthetic"] = "synthetic"


class CalibratedProfile(SimulationProfile):
    kind: Literal["calibrated"] = "calibrated"
