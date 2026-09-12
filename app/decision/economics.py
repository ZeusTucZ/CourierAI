from app.decision.timing import WorkPlan
from app.models.requests import DecideRequest
from app.models.responses import Economics
from app.models.strategy import StrategySnapshot


def calculate_economics(order: DecideRequest, snapshot: StrategySnapshot,
                        plan: WorkPlan) -> Economics:
    profile = snapshot.vehicle_profiles[order.vehicle]
    gross = order.base_pay_mxn * order.surge_multiplier + order.est_tip_mxn
    cost = (order.distance_pickup_km + order.distance_delivery_km) * profile.operating_cost_mxn_per_km
    net = gross - cost
    # Conservative opportunity cost: charge all committed time to this offer;
    # never count already accepted orders' revenue twice.
    raw = net / plan.total_time_min * 60
    return Economics(
        gross_pay_mxn=gross, operating_cost_mxn=cost, net_pay_mxn=net,
        total_time_min=plan.total_time_min, raw_rate_mxn_hr=raw,
        adjusted_rate_mxn_hr=raw + snapshot.zone_values.get(order.zone_dropoff, 0),
        reservation_wage_mxn_hr=snapshot.reservation_wage_mxn_hr,
        deadhead_km=order.distance_pickup_km,
    )
