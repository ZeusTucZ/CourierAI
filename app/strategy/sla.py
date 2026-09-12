from datetime import timedelta


def compute_delivery_deadline(order, state, policy):
    """Configured SLA, not a measured industry promise; decision_deadline is unrelated.

    Simulator supplies the shock-adjusted travel estimates visible at acceptance.
    """
    if order.estimated_pickup_min is None or order.estimated_delivery_min is None:
        raise ValueError("SLA requires prepared travel estimates")
    service = order.estimated_pickup_min + order.estimated_delivery_min + order.restaurant_prep_min
    if policy.sla_distance_buckets:
        bucket = next((b for b in policy.sla_distance_buckets
                       if order.distance_delivery_km <= b.distance_upper_km), None)
        if bucket is not None:
            # Empirical total duration P90; never shorten currently visible physical work.
            return order.sim_time + timedelta(minutes=max(service, bucket.p90_min))
    return order.sim_time + timedelta(minutes=max(1, service) * policy.sla_time_multiplier + policy.sla_buffer_min)
