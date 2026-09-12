from types import MappingProxyType
from typing import Mapping

from pydantic import Field, field_serializer, field_validator

from app.config.policy import PolicyConfig
from app.config.vehicles import VehicleProfile, default_vehicle_profiles
from app.models.common import Finite, Model, NonNegative, Vehicle


class StrategySnapshot(Model):
    version: str = "mvp1-v1"
    is_stale: bool = False
    reservation_wage_mxn_hr: NonNegative = 165
    zone_values: Mapping[int, Finite] = Field(default_factory=lambda: {7: 15.0, 11: -15.0}, validate_default=True)
    flagged_zones: frozenset[int] = frozenset({11})
    vehicle_profiles: Mapping[Vehicle, VehicleProfile] = Field(default_factory=default_vehicle_profiles, validate_default=True)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)

    @field_validator("zone_values", "vehicle_profiles")
    @classmethod
    def freeze_mapping(cls, value, info):
        if info.field_name == "vehicle_profiles" and set(value) != {"moto", "car", "bike"}:
            raise ValueError("Profiles for moto, car and bike are required")
        return MappingProxyType(dict(value))

    @field_serializer("zone_values", "vehicle_profiles")
    def serialize_mapping(self, value):
        return dict(value)

    @field_serializer("flagged_zones")
    def serialize_zones(self, value):
        return sorted(value)
