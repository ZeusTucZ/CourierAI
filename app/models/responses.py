from typing import Any, Literal

from pydantic import field_validator, model_serializer

from app.models.common import Finite, Model, NonNegative

Constraint = Literal["flagged_zone_night", "mandatory_break", "heat_rule",
                     "shift_end_infeasible", "vehicle_capacity", "reservation_wage"]
Decision = Literal["ACCEPT", "SKIP"]


class Economics(Model):
    gross_pay_mxn: Finite
    operating_cost_mxn: NonNegative
    net_pay_mxn: Finite
    total_time_min: NonNegative
    raw_rate_mxn_hr: Finite
    adjusted_rate_mxn_hr: Finite
    reservation_wage_mxn_hr: NonNegative
    deadhead_km: NonNegative
    zone_value_mxn_hr: Finite | None = None
    opportunity_cost_mxn: NonNegative | None = None
    skip_penalty_mxn: NonNegative | None = None
    stacking_time_min: NonNegative | None = None

    @model_serializer(mode="wrap")
    def serialize_economics(self, handler):
        # Old snapshots retain the original MVP 1/2 economics representation.
        return {key: value for key, value in handler(self).items() if value is not None}


class DecideResponse(Model):
    order_id: str
    decision: Decision
    reason: str
    binding_constraint: Constraint | None = None
    latency_ms: NonNegative
    tier: Literal["tier1"] = "tier1"
    degraded: bool = False
    economics: Economics | None = None
    gemini_enabled: bool = False
    gemini_model: str | None = None
    gemini_advice: dict[str, Any] | None = None
    gemini_confidence: float | None = None
    gemini_demand_outlook: str | None = None
    gemini_destination_quality: str | None = None
    gemini_opportunity_risk: str | None = None
    llm_adjustment_mxn_hr: float = 0
    pre_llm_adjusted_rate: float | None = None
    post_llm_adjusted_rate: float | None = None
    llm_changed_decision: bool = False
    llm_explanation: str | None = None
    gemini_latency_ms: float | None = None
    gemini_cache_hit: bool = False
    gemini_error: str | None = None

    @model_serializer(mode="wrap")
    def serialize_response(self, handler):
        data = handler(self)
        if data.get("economics") is None:
            data.pop("economics", None)
        return data

    @field_validator("reason")
    @classmethod
    def short_reason(cls, value):
        if not value.strip() or len(value.split()) >= 40:
            raise ValueError("reason must contain between 1 and 39 words")
        return value


class Alternative(Model):
    option: Decision
    rejected_because: str


class DecisionRecord(DecideResponse):
    sim_time: str
    inputs: dict[str, Any]
    strategy_snapshot: dict[str, Any]
    alternatives_considered: tuple[Alternative, ...]
    decision_details: dict[str, Any] | None = None
    structured_reason: str | None = None

    @model_serializer(mode="wrap")
    def serialize_record(self, handler):
        # Audit records explicitly retain economics=null for hard refusals.
        data = handler(self)
        if data.get("decision_details") is None:
            data.pop("decision_details", None)
        return data
