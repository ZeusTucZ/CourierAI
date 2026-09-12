from app.decision.timing import WorkPlan
from app.models.requests import DecideRequest
from app.models.responses import Economics
from app.models.strategy import StrategySnapshot
from app.strategy.opportunity_cost import opportunity_cost


def calculate_economics(order: DecideRequest, snapshot: StrategySnapshot,
                        plan: WorkPlan) -> Economics:
    profile = snapshot.vehicle_profiles[order.vehicle]
    gross = order.base_pay_mxn * order.surge_multiplier + order.est_tip_mxn
    cost = (order.distance_pickup_km + order.distance_delivery_km) * profile.operating_cost_mxn_per_km
    net = gross - cost
    # Conservative opportunity cost: charge all committed time to this offer;
    # never count already accepted orders' revenue twice.
    raw = net / plan.total_time_min * 60
    zone_value = snapshot.zone_values.get(order.zone_dropoff, 0)
    prediction = snapshot.zone_predictions.get(order.zone_pickup)
    opportunity = opportunity_cost(prediction.expected_net_mxn_per_hour if prediction else 0,
                                   plan.total_time_min, snapshot.opportunity_fraction) if snapshot.economics_v2 else 0
    skip = snapshot.skip_penalty_mxn if snapshot.economics_v2 else 0
    return Economics(
        gross_pay_mxn=gross, operating_cost_mxn=cost, net_pay_mxn=net,
        total_time_min=plan.total_time_min, raw_rate_mxn_hr=raw,
        adjusted_rate_mxn_hr=raw + zone_value + (skip - opportunity) / plan.total_time_min * 60,
        reservation_wage_mxn_hr=snapshot.reservation_wage_mxn_hr,
        deadhead_km=order.distance_pickup_km,
        **({"zone_value_mxn_hr": zone_value, "opportunity_cost_mxn": opportunity,
            "skip_penalty_mxn": skip, "stacking_time_min": max(0, plan.total_time_min - plan.new_order_time_min)}
           if snapshot.economics_v2 else {}),
    )
