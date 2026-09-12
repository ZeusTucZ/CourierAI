from typing import Protocol

from app.models.requests import DecideRequest
from app.models.responses import DecideResponse
from app.models.strategy import StrategySnapshot
from app.simulation.state import CourierState


def decision_request(order: DecideRequest, state: CourierState) -> DecideRequest:
    return DecideRequest.model_validate({**order.model_dump(), "courier_state_overrides": state.overrides()})


class Agent(Protocol):
    name: str
    snapshot: StrategySnapshot

    def decide(self, order: DecideRequest, courier_state: CourierState) -> DecideResponse: ...

    def decide_request(self, request: DecideRequest) -> DecideResponse: ...
