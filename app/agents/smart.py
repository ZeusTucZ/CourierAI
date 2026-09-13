from app.agents.base import decision_request
from app.decision.engine import DecisionService
from app.logging.decision_log import DecisionLog
from app.models.strategy import StrategySnapshot
from app.services.strategy_store import StrategyStore
from app.strategy.opportunity_cost import opportunity_cost
from app.strategy.smart_v2 import batch_score, idle_score, zone_value_mxn


class SmartAgent:
    name = "SmartAgent"

    def __init__(self, snapshot: StrategySnapshot | None = None):
        self.snapshot = snapshot or StrategySnapshot()
        self.service = DecisionService(StrategyStore(self.snapshot), DecisionLog())

    def decide(self, order, courier_state):
        return self.decide_request(decision_request(order, courier_state))

    def decide_request(self, request):
        return self.service.decide(request)

    def score_route_candidate(self, order, *, current_plan, candidate_plan,
                              current_distance_km, candidate_distance_km,
                              minimum_sla_margin_min, policy):
        """Score simulator-provided route facts without owning routing or safety."""
        incremental_distance = max(0.0, candidate_distance_km - current_distance_km)
        incremental_time = max(0.0, candidate_plan.total_time_min - current_plan.total_time_min)
        profile = self.snapshot.vehicle_profiles[order.vehicle]
        gross = order.base_pay_mxn * order.surge_multiplier + order.est_tip_mxn
        incremental_cost = incremental_distance * profile.operating_cost_mxn_per_km
        incremental_net = gross - incremental_cost
        active = bool(order.courier_state_overrides and
                      order.courier_state_overrides.in_flight_orders)
        mode = "batching" if active else "idle"
        prediction = self.snapshot.zone_predictions.get(order.zone_pickup)
        expected_rate = (prediction.expected_net_mxn_per_hour or 0) if prediction else 0
        opportunity = opportunity_cost(expected_rate, candidate_plan.new_order_time_min,
                                       policy.opportunity_fraction)
        dropoff = zone_value_mxn(self.snapshot.zone_values.get(order.zone_dropoff, 0),
                                 candidate_plan.new_order_time_min)
        if mode == "idle":
            score = idle_score(net_pay_mxn=incremental_net,
                opportunity_cost_mxn=opportunity, dropoff_value_mxn=dropoff,
                service_time_min=candidate_plan.new_order_time_min,
                commitment_horizon_min=candidate_plan.total_time_min,
                reservation_wage_mxn_hr=self.snapshot.reservation_wage_mxn_hr,
                commitment_free_window_min=policy.commitment_free_window_min,
                commitment_cost_per_min=policy.commitment_cost_per_min)
        else:
            score = batch_score(incremental_net_pay_mxn=incremental_net,
                incremental_time_min=incremental_time,
                minimum_sla_margin_min=minimum_sla_margin_min,
                reservation_wage_mxn_hr=self.snapshot.reservation_wage_mxn_hr,
                preferred_sla_buffer_min=policy.preferred_sla_buffer_min,
                sla_risk_cost_per_min=policy.sla_risk_cost_per_min)
        cause = None if score.final_score >= 0 else (
            "commitment_penalty" if mode == "idle" and score.commitment_penalty_mxn > 0
            else "sla_risk" if mode == "batching" and score.sla_risk_penalty_mxn > 0
            else "batch_incremental_value" if mode == "batching" else "economic_threshold")
        return {
            "mode": mode, "decision_cause": cause, "net_pay_mxn": incremental_net,
            "service_time_min": candidate_plan.new_order_time_min,
            "commitment_horizon_min": candidate_plan.total_time_min,
            "commitment_penalty_mxn": score.commitment_penalty_mxn,
            "opportunity_cost_mxn": opportunity if mode == "idle" else None,
            "dropoff_value_mxn": dropoff if mode == "idle" else None,
            "current_plan_distance_km": current_distance_km,
            "candidate_plan_distance_km": candidate_distance_km,
            "incremental_distance_km": incremental_distance,
            "current_plan_eta_min": current_plan.total_time_min,
            "candidate_plan_eta_min": candidate_plan.total_time_min,
            "incremental_time_min": incremental_time,
            "incremental_operating_cost_mxn": incremental_cost,
            "incremental_net_pay_mxn": incremental_net,
            "minimum_sla_margin_min": minimum_sla_margin_min,
            "sla_risk_penalty_mxn": score.sla_risk_penalty_mxn,
            "required_time_value_mxn": score.required_time_value_mxn,
            "final_score_mxn": score.final_score,
        }
