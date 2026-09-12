from dataclasses import dataclass

from app.strategy.opportunity_cost import opportunity_cost


@dataclass(frozen=True)
class CancellationDecision:
    cancel: bool
    continue_value: float
    cancel_value: float
    reason: str


class CancellationPolicy:
    def __init__(self, policy):
        self.policy = policy

    def evaluate(self, *, triggering_shock, remaining_net, remaining_min, lateness_min, expected_rate, infeasible=False):
        opportunity = opportunity_cost(expected_rate, remaining_min, self.policy.opportunity_fraction)
        cont = remaining_net - self.policy.lateness_penalty_mxn_per_min * lateness_min - opportunity
        cancel = -self.policy.cancellation_penalty_mxn + opportunity
        eligible = triggering_shock is not None and triggering_shock.get("shock_type") in {"closure", "rain", "delay"}
        justified = cancel > cont + self.policy.cancellation_min_gain
        allowed = eligible and self.policy.use_cancellation and (lateness_min > 0 or infeasible) and justified
        return CancellationDecision(allowed, cont, cancel, "disruption_value_comparison" if allowed else "continue_or_ineligible")
