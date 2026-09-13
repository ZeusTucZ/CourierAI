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
    def evaluate(self, order: DecideRequest, snapshot: StrategySnapshot, plan: WorkPlan | None = None,
                 advice=None, llm_config=None, gemini_cache_hit=False, gemini_latency_ms=None,
                 gemini_error=None) -> Evaluation:
        start = perf_counter_ns()
        state = resolve_state(order.sim_time, order.courier_state_overrides,
                              snapshot.policy.default_shift_hours)
        plan = plan or build_work_plan(order, state, snapshot)
        violation = evaluate_constraints(order, state, snapshot, plan)
        economics = None
        pre_rate = post_rate = None
        llm_adjustment = 0.0
        changed = False
        if violation:
            decision, binding, reason = "SKIP", violation.constraint, violation.reason
        else:
            economics = calculate_economics(order, snapshot, plan)
            pre_rate = economics.adjusted_rate_mxn_hr
            if advice is not None and llm_config is not None:
                from app.llm.fallback import adjustment
                llm_adjustment = adjustment(advice, llm_config.min_adjustment, llm_config.max_adjustment)
            post_rate = pre_rate + llm_adjustment
            accepted = post_rate >= snapshot.reservation_wage_mxn_hr
            changed = accepted != (pre_rate >= snapshot.reservation_wage_mxn_hr)
            decision = "ACCEPT" if accepted else "SKIP"
            binding = None if accepted else "reservation_wage"
            reason = economic_reason(accepted, economics) if not changed else (
                f"Post-LLM adjusted rate {post_rate:.2f} MXN/hr is "
                f"{'at or above' if accepted else 'below'} reservation wage "
                f"{snapshot.reservation_wage_mxn_hr:.2f} MXN/hr.")
        response = DecideResponse(
            order_id=order.order_id, decision=decision, binding_constraint=binding,
            reason=reason, economics=economics,
            degraded=snapshot.is_stale or bool(llm_config and llm_config.enabled and advice is None),
            latency_ms=(perf_counter_ns() - start) / 1_000_000,
            gemini_enabled=bool(llm_config and llm_config.enabled),
            gemini_model=llm_config.model if llm_config and llm_config.enabled else None,
            gemini_advice=advice.model_dump(mode='json') if advice else None,
            gemini_confidence=advice.confidence if advice else None,
            gemini_demand_outlook=advice.demand_outlook if advice else None,
            gemini_destination_quality=advice.destination_quality if advice else None,
            gemini_opportunity_risk=advice.opportunity_risk if advice else None,
            llm_adjustment_mxn_hr=llm_adjustment,
            pre_llm_adjusted_rate=pre_rate, post_llm_adjusted_rate=post_rate,
            llm_changed_decision=changed, gemini_cache_hit=gemini_cache_hit,
            gemini_latency_ms=gemini_latency_ms, gemini_error=gemini_error,
        )
        return Evaluation(response, state, plan)


class DecisionService:
    def __init__(self, strategies: StrategyStore, log: DecisionLog, advisor=None):
        self.strategies = strategies
        self.log = log
        self.engine = DecisionEngine()
        self.advisor = advisor
        self.llm_changed_decisions = self.llm_changed_to_accept = self.llm_changed_to_skip = 0

    def decide(self, order: DecideRequest, started_ns: int | None = None, plan: WorkPlan | None = None) -> DecideResponse:
        start = started_ns if started_ns is not None else perf_counter_ns()
        snapshot = self.strategies.get()  # One coherent snapshot per decision.
        advice = entry = None
        if self.advisor is not None and self.advisor.config.enabled:
            from app.llm.strategy_advisor import observable_context
            context = observable_context(order, snapshot)
            entry = self.advisor.get(context, snapshot.version)
            advice = entry.advice if entry else None
        if self.advisor is None:
            result = self.engine.evaluate(order, snapshot) if plan is None else self.engine.evaluate(order, snapshot, plan)
        else:
            result = self.engine.evaluate(order, snapshot, plan, advice=advice,
                llm_config=self.advisor.config,
                gemini_cache_hit=entry is not None,
                gemini_latency_ms=entry.latency_ms if entry else None,
                gemini_error=(self.advisor.last_error or ('Gemini disabled or API key missing' if not self.advisor.config.api_key else 'No cached advisory'))
                    if not entry and self.advisor.config.enabled else None)
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
            structured_reason=response.reason,
            strategy_snapshot=snapshot.model_dump(mode="json"),
            alternatives_considered=(Alternative(
                option="SKIP" if response.decision == "ACCEPT" else "ACCEPT",
                rejected_because=response.reason,
            ),),
        )
        record = DecisionRecord(**record_data)
        # Includes state resolution, evaluation, explanation, audit copying/append.
        latency = self.log.append(record, start)
        if response.llm_changed_decision:
            self.llm_changed_decisions += 1
            if response.decision == 'ACCEPT':
                self.llm_changed_to_accept += 1
            else:
                self.llm_changed_to_skip += 1
        response = response.model_copy(update={"latency_ms": latency})
        return response

    def gemini_metrics(self):
        metrics = self.advisor.metrics() if self.advisor else {}
        return {**metrics, 'llm_changed_decisions': self.llm_changed_decisions,
            'llm_changed_to_accept': self.llm_changed_to_accept,
            'llm_changed_to_skip': self.llm_changed_to_skip,
            'net_gain_from_llm_changed_decisions': None}
