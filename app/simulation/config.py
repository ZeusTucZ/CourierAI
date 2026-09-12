"""Synthetic experiment parameters, not calibrated observations."""
from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field, model_validator

from app.models.common import Model, NonNegative, Positive, Vehicle
from app.calibration.profiles import SimulationProfile


class Range(Model):
    low: NonNegative
    high: NonNegative

    @model_validator(mode="after")
    def ordered(self):
        if self.low > self.high:
            raise ValueError("Range low must not exceed high")
        return self


class ScheduledShock(Model):
    at_min: NonNegative
    shock_type: Literal["surge", "closure", "rain", "delay"]
    zone: int | None = None
    road: str | None = None
    multiplier: Positive | None = None
    duration_min: Positive | None = None
    order_id: str | None = None
    slip_min: NonNegative | None = None

    @model_validator(mode="after")
    def sufficient_fields(self):
        if self.shock_type == "surge" and self.zone is None:
            raise ValueError("Surge requires zone")
        if self.shock_type == "closure" and self.zone is None and self.road is None:
            raise ValueError("Closure requires zone or road")
        if self.shock_type == "surge" and self.multiplier is None:
            raise ValueError("Surge requires multiplier")
        if self.shock_type != "delay" and self.duration_min is None:
            raise ValueError("Transient shocks require duration_min")
        if self.shock_type == "delay" and (self.order_id is None or self.slip_min is None):
            raise ValueError("Delay requires order_id and slip_min")
        return self


class SyntheticConfig(Model):
    simulation_start_time: datetime = datetime(2026, 3, 21, 15)
    zone_count: int = Field(default=12, ge=1, strict=True)
    order_interval_min: Range = Range(low=2, high=6)
    distance_pickup_km: Range = Range(low=0.3, high=3)
    distance_delivery_km: Range = Range(low=0.5, high=6)
    base_pay_mxn: Range = Range(low=35, high=120)
    tip_mxn: Range = Range(low=0, high=20)
    prep_min: Range = Range(low=0, high=8)
    weight_kg: Range = Range(low=0.5, high=6)
    volume_liters: Range = Range(low=1, high=12)
    initial_surge_multiplier: Positive = 1
    rain_travel_time_multiplier: Positive = 1.25
    closure_delay_min: NonNegative = 5
    # One rain event in the middle of a shift guarantees a demo shock.
    # Explicit () disables shocks for controlled experiments.
    shock_schedule: tuple[ScheduledShock, ...] | None = None
    default_rain_fraction_of_shift: float = Field(default=0.5, ge=0, lt=1, allow_inf_nan=False)
    default_rain_duration_min: Positive = 30

    @model_validator(mode="after")
    def positive_interval(self):
        if self.order_interval_min.low < 0.000001:
            raise ValueError("Order intervals must advance at least one micro-minute")
        if self.rain_travel_time_multiplier < 1:
            raise ValueError("Rain cannot accelerate travel in this synthetic model")
        return self


class ShiftConfig(Model):
    seed: int = Field(strict=True)
    shift_hours: Positive
    vehicle: Vehicle
    start_location_zone: int = Field(strict=True)
    # Explicitly separate simulator assumptions from the four official fields.
    simulation: SyntheticConfig = Field(default_factory=SyntheticConfig)
    profile: SimulationProfile | None = None

    @model_validator(mode="after")
    def valid_shift(self):
        if self.profile and any(max(t.pickup, t.dropoff) > self.simulation.zone_count for t in self.profile.zone_transition_distribution):
            raise ValueError("Profile zones exceed configured zone_count")
        if not 1 <= self.start_location_zone <= self.simulation.zone_count:
            raise ValueError("start_location_zone must be within synthetic zone_count")
        try:
            end = self.shift_end
        except OverflowError as exc:
            raise ValueError("Shift end exceeds datetime bounds") from exc
        if end <= self.simulation.simulation_start_time:
            raise ValueError("Shift duration must advance simulated time")
        for shock in self.simulation.shock_schedule or ():
            if shock.at_min >= self.shift_hours * 60:
                raise ValueError("Scheduled shocks must occur before shift end")
            if shock.zone is not None and not 1 <= shock.zone <= self.simulation.zone_count:
                raise ValueError("Shock zone must be within synthetic zone_count")
        return self

    @property
    def shift_end(self) -> datetime:
        return self.simulation.simulation_start_time + timedelta(hours=self.shift_hours)
