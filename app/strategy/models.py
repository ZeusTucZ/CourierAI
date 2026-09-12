from pydantic import Field, model_validator

from app.models.common import Model, NonNegative, Positive


class ZonePrediction(Model):
    zone: int
    time_bucket: int = Field(ge=0, le=23)
    expected_orders_per_hour: NonNegative = 0
    expected_gross_pay: NonNegative = 0
    expected_net_pay: float = Field(default=0, allow_inf_nan=False)
    expected_wait_time_min: NonNegative | None = None
    expected_net_mxn_per_hour: NonNegative = 0
    sample_count: int = Field(default=0, ge=0)
    confidence: float = Field(default=0, ge=0, le=1)
    fallback: bool = False


class StrategyPolicy(Model):
    zone_value_clip: NonNegative = 50
    base_reservation_wage: NonNegative = 165
    min_reservation_wage: NonNegative = 80
    max_reservation_wage: NonNegative = 250
    demand_adjustment_fraction: NonNegative = .1
    final_hour_discount: NonNegative = 20
    opportunity_fraction: float = Field(default=.25, ge=0, le=1)
    update_interval_min: Positive = 30
    minimum_reposition_gain: NonNegative = 5
    minimum_dwell_time_min: NonNegative = 30
    reposition_horizon_min: Positive = 30
    synthetic_zone_spacing_km: Positive = .5
    max_active_orders: int = Field(default=4, ge=1, le=6)
    max_insertions: int = Field(default=32, ge=1, le=64)
    sla_time_multiplier: Positive = 1.5
    sla_buffer_min: NonNegative = 10
    skip_penalty_mxn: NonNegative = 0
    cancellation_penalty_mxn: NonNegative = 20
    lateness_penalty_mxn_per_min: NonNegative = 1
    cancellation_min_gain: NonNegative = 5
    use_zone_value: bool = True
    use_reposition: bool = True
    use_improved_batching: bool = True
    use_historical_prediction: bool = True
    use_cancellation: bool = True

    @model_validator(mode="after")
    def bounds(self):
        if self.min_reservation_wage > self.max_reservation_wage:
            raise ValueError("Reservation wage bounds reversed")
        return self
