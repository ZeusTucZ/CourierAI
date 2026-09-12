from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.models.common import Model, NonNegative, Vehicle
from app.models.state import CourierStateOverrides


class DecideRequest(Model):
    event: Literal["order_offered"] = "order_offered"
    order_id: str
    platform: Literal["rappi", "didi", "uber"] | None = None
    sim_time: datetime
    decision_deadline: datetime | None = None
    zone_pickup: int = Field(strict=True)
    zone_dropoff: int = Field(strict=True)
    zone_pickup_name: str | None = None
    zone_dropoff_name: str | None = None
    distance_pickup_km: NonNegative
    distance_delivery_km: NonNegative
    base_pay_mxn: NonNegative
    est_tip_mxn: NonNegative = 0
    surge_multiplier: NonNegative
    restaurant_prep_min: NonNegative = 0
    weight_kg: NonNegative | None = None
    volume_liters: NonNegative | None = None
    vehicle: Vehicle
    estimated_pickup_min: NonNegative | None = None
    estimated_delivery_min: NonNegative | None = None
    courier_state_overrides: CourierStateOverrides | None = None

    @model_validator(mode="after")
    def consistent_timezones(self):
        values = [self.decision_deadline]
        if self.courier_state_overrides:
            values += [self.courier_state_overrides.shift_end_time,
                       self.courier_state_overrides.last_break_end_time]
        for value in values:
            if value is not None and (value.utcoffset() is None) != (self.sim_time.utcoffset() is None):
                raise ValueError("All timestamps must consistently include or omit timezone offsets")
        return self
