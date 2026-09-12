import math
from statistics import mean

from app.metrics.results import ShiftMetrics
from app.simulation.events import Event, event_time


def collect_metrics(events: list[Event]) -> ShiftMetrics:
    """Reconstruct from recorded decisions and cumulative execution accounting."""
    if not events or events[0]["event"] != "shift_start" or events[-1]["event"] != "shift_end":
        raise ValueError("Metrics require a complete shift log")
    end = events[-1]
    earnings = [event for event in events if event["event"] == "earnings_update"]
    if not earnings:
        raise ValueError("Missing final execution accounting")
    actual = earnings[-1]
    decisions = [event for event in events if event["event"] == "decision"]
    offered = sum(event["event"] == "order_offered" for event in events)
    if offered != len(decisions):
        raise ValueError("Every offer must have exactly one decision")
    accepted = sum(event["decision"] == "ACCEPT" for event in decisions)
    completed = actual["orders_completed"]
    gross, costs = actual["gross_earnings_mxn"], actual["operating_costs_mxn"]
    net = gross - costs
    distance = actual["distance_traveled_km"]
    latencies = sorted(event["latency_ms"] for event in decisions)
    hours = (event_time(end) - event_time(events[0])).total_seconds() / 3600
    return ShiftMetrics(
        gross, costs, net, offered, accepted, offered - accepted, completed, distance,
        actual["idle_time_min"], actual["late_deliveries"], actual["safety_violations"],
        mean(latencies) if latencies else 0,
        latencies[math.ceil(len(latencies) * .95) - 1] if latencies else 0,
        net / hours, net / distance if distance else None, accepted - completed,
        end["post_accept_infeasible"],
    )
