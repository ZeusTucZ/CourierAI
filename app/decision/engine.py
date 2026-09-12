from dataclasses import dataclass
from time import perf_counter_ns

from app.decision.constraints import evaluate_constraints
from app.decision.economics import calculate_economics
from app.decision.explanations import economic_reason
from app.decision.timing import WorkPlan, build_work_plan
from app.logging.decision_log import DecisionLog
from app.models.requests import DecideRequest
from app.models.responses import Alternative, DecideResponse, DecisionRecord
from app.models.state import CourierState, resolve_state
from app.models.strategy import StrategySnapshot
from app.services.strategy_store import StrategyStore


@dataclass(frozen=True)
class Evaluation:
    response: DecideResponse
    state: CourierState
    plan: WorkPlan


class DecisionEngine:
    def evaluate(self, order: DecideRequest, snapshot: StrategySnapshot) -> Evaluation:
        start = perf_counter_ns()
        state = resolve_state(order.sim_time, order.courier_state_overrides,
                              snapshot.policy.default_shift_hours)
        plan = build_work_plan(order, state, snapshot)
        violation = evaluate_constraints(order, state, snapshot, plan)
        economics = None
        if violation:
            decision, binding, reason = "SKIP", violation.constraint, violation.reason
        else:
            economics = calculate_economics(order, snapshot, plan)
            accepted = economics.adjusted_rate_mxn_hr >= snapshot.reservation_wage_mxn_hr
            decision = "ACCEPT" if accepted else "SKIP"
            binding = None if accepted else "reservation_wage"
            reason = economic_reason(accepted, economics)
        response = DecideResponse(
            order_id=order.order_id, decision=decision, binding_constraint=binding,
            reason=reason, economics=economics, degraded=snapshot.is_stale,
            latency_ms=(perf_counter_ns() - start) / 1_000_000,
        )
        return Evaluation(response, state, plan)


class DecisionService:
    def __init__(self, strategies: StrategyStore, log: DecisionLog):
        self.strategies = strategies
        self.log = log
        self.engine = DecisionEngine()

    def decide(self, order: DecideRequest, started_ns: int | None = None) -> DecideResponse:
        start = started_ns if started_ns is not None else perf_counter_ns()
        snapshot = self.strategies.get()  # One coherent snapshot per decision.
        result = self.engine.evaluate(order, snapshot)
        response, state, plan = result.response, result.state, result.plan
        inputs = {
            "request": order.model_dump(mode="json", exclude_unset=True),
            "courier_state": state.model_dump(mode="json"),
            "position": None,  # No current-position field in the decide contract.
            "time_remaining_min": (state.shift_end_time - order.sim_time).total_seconds() / 60,
            "time_to_completion_min": plan.total_time_min,
            "estimated_completion_time": plan.completion_time.isoformat(),
            "new_order_time_min": plan.new_order_time_min,
            "committed_riding_min": plan.riding_min,
            "timing_is_complete": not plan.unknown_timing,
        }
        record_data = dict(
            **response.model_dump(), sim_time=order.sim_time.isoformat(), inputs=inputs,
            strategy_snapshot=snapshot.model_dump(mode="json"),
            alternatives_considered=(Alternative(
                option="SKIP" if response.decision == "ACCEPT" else "ACCEPT",
                rejected_because=response.reason,
            ),),
        )
        record = DecisionRecord(**record_data)
        # Includes state resolution, evaluation, explanation, audit copying/append.
        latency = self.log.append(record, start)
        response = response.model_copy(update={"latency_ms": latency})
        return response
