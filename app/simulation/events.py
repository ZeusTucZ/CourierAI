"""Official public event names; queue-only consequences never leak as new types."""
from datetime import datetime
from typing import Any, Literal

from pydantic import model_validator

from app.models.common import Model, NonNegative, Positive

Event = dict[str, Any]
PUBLIC_EVENTS = frozenset({"shift_start", "order_offered", "shock", "decision",
                           "position_update", "earnings_update", "strategy_update", "shift_end"})


class Shock(Model):
    event: Literal["shock"] = "shock"
    sim_time: datetime
    shock_type: Literal["surge", "closure", "rain", "delay"]
    zone: int | None = None
    multiplier: Positive | None = None
    road: str | None = None
    order_id: str | None = None
    slip_min: NonNegative | None = None
    duration_min: Positive | None = None

    @model_validator(mode="after")
    def actionable(self):
        if self.shock_type == "surge" and self.zone is None:
            raise ValueError("Surge requires zone")
        if self.shock_type == "closure" and self.zone is None and self.road is None:
            raise ValueError("Closure requires zone or road")
        if self.shock_type == "surge" and self.multiplier is None:
            raise ValueError("Surge requires multiplier")
        if self.shock_type != "delay" and self.duration_min is None:
            raise ValueError("Transient shock requires duration_min")
        if self.shock_type == "delay" and (self.order_id is None or self.slip_min is None):
            raise ValueError("Delay requires order_id and slip_min")
        return self


def event_time(event: Event) -> datetime:
    return datetime.fromisoformat(event["sim_time"])
