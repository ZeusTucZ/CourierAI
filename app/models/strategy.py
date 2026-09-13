from types import MappingProxyType
from datetime import datetime
from typing import Mapping

from pydantic import Field, field_serializer, field_validator

from app.config.policy import PolicyConfig
from app.config.vehicles import VehicleProfile, default_vehicle_profiles
from app.models.common import Finite, Model, NonNegative, Vehicle
from app.strategy.models import ZonePrediction


class StrategySnapshot(Model):
    version: str = "mvp1-v1"
    is_stale: bool = False
    reservation_wage_mxn_hr: NonNegative = 165
    zone_values: Mapping[int, Finite] = Field(default_factory=lambda: {7: 15.0, 11: -15.0}, validate_default=True)
    # Zone 99 is the public probe's designated flagged zone. It is outside the
    # synthetic map, so it cannot affect generated shifts, but keeps /decide
    # aligned with the published endpoint contract.
    flagged_zones: frozenset[int] = frozenset({11, 99})
    vehicle_profiles: Mapping[Vehicle, VehicleProfile] = Field(default_factory=default_vehicle_profiles, validate_default=True)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    strategy_version: str = "mvp1"
    generated_at_sim_time: datetime | None = None
    target_zone: int | None = None
    zone_predictions: Mapping[int, ZonePrediction] = Field(default_factory=dict, validate_default=True)
    economics_v2: bool = False
    opportunity_fraction: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    skip_penalty_mxn: NonNegative = 0

    @field_validator("zone_values", "vehicle_profiles", "zone_predictions")
    @classmethod
    def freeze_mapping(cls, value, info):
        if info.field_name == "vehicle_profiles" and set(value) != {"moto", "car", "bike"}:
            raise ValueError("Profiles for moto, car and bike are required")
        return MappingProxyType(dict(value))

    @field_serializer("zone_values", "vehicle_profiles", "zone_predictions")
    def serialize_mapping(self, value):
        return dict(value)

    @field_serializer("flagged_zones")
    def serialize_zones(self, value):
        return sorted(value)
