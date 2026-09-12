from time import perf_counter_ns

from app.agents.base import decision_request
from app.decision.constraints import evaluate_constraints
from app.decision.economics import calculate_economics
from app.decision.timing import build_work_plan
from app.models.responses import DecideResponse
from app.models.state import resolve_state
from app.models.strategy import StrategySnapshot


class GreedyRateBaseline:
    """Immediate new-order rate; same feasibility functions and physical parameters."""
    name = "GreedyRateBaseline"

    def __init__(self, snapshot: StrategySnapshot | None = None, threshold: float | None = None):
        source = snapshot or StrategySnapshot()
        self.snapshot = StrategySnapshot.model_validate({
            **source.model_dump(mode="json"), "zone_values": {},
            "reservation_wage_mxn_hr": source.reservation_wage_mxn_hr if threshold is None else threshold,
            "version": source.version + ":greedy-rate",
        })

    def decide(self, order, courier_state):
        return self.decide_request(decision_request(order, courier_state))

    def decide_request(self, request):
        start = perf_counter_ns()
        strategy = self.snapshot
        state = resolve_state(request.sim_time, request.courier_state_overrides,
                              strategy.policy.default_shift_hours)
        plan = build_work_plan(request, state, strategy)
        violation = evaluate_constraints(request, state, strategy, plan)
        economics = None
        if violation:
            decision, binding, reason = "SKIP", violation.constraint, violation.reason
        else:
            economics = calculate_economics(request, strategy, plan)
            # Pending work is checked for feasibility, but baseline ranks the
            # incremental order by its immediate service time, not strategic value.
            rate = economics.net_pay_mxn / plan.new_order_time_min * 60
            economics = economics.model_copy(update={"total_time_min": plan.new_order_time_min,
                                                     "raw_rate_mxn_hr": rate, "adjusted_rate_mxn_hr": rate})
            accepted = rate >= strategy.reservation_wage_mxn_hr
            decision = "ACCEPT" if accepted else "SKIP"
            binding = None if accepted else "reservation_wage"
            comparison = "meets or exceeds" if accepted else "is below"
            reason = (f"{'Accepted' if accepted else 'Skipped'}: immediate net rate MXN {rate!r}/hr "
                      f"{comparison} reservation_wage MXN {strategy.reservation_wage_mxn_hr!r}/hr.")
        return DecideResponse(order_id=request.order_id, decision=decision, reason=reason,
                              binding_constraint=binding, economics=economics,
                              latency_ms=(perf_counter_ns() - start) / 1e6, degraded=strategy.is_stale)
