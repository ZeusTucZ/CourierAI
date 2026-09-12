def opportunity_cost(expected_zone_net_rate: float, committed_time_min: float,
                     fraction: float = 1) -> float:
    """MXN forgone = nonnegative historical MXN/hour × occupied hours × fraction."""
    if committed_time_min < 0 or not 0 <= fraction <= 1:
        raise ValueError("Invalid commitment duration or opportunity fraction")
    return max(0, expected_zone_net_rate) * committed_time_min / 60 * fraction
