from app.agents.base import decision_request
from app.decision.engine import DecisionService
from app.logging.decision_log import DecisionLog
from app.models.strategy import StrategySnapshot
from app.services.strategy_store import StrategyStore


class SmartAgent:
    name = "SmartAgent"

    def __init__(self, snapshot: StrategySnapshot | None = None):
        self.snapshot = snapshot or StrategySnapshot()
        self.service = DecisionService(StrategyStore(self.snapshot), DecisionLog())

    def decide(self, order, courier_state):
        return self.decide_request(decision_request(order, courier_state))

    def decide_request(self, request):
        return self.service.decide(request)
