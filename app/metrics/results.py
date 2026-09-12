from dataclasses import asdict, dataclass

from app.logging.event_log import EventLog
from app.simulation.state import CourierState


@dataclass(frozen=True)
class ShiftMetrics:
    gross_earnings_mxn: float
    operating_costs_mxn: float
    net_earnings_mxn: float
    orders_offered: int
    orders_accepted: int
    orders_skipped: int
    orders_completed: int
    distance_traveled_km: float
    idle_time_min: float
    late_deliveries: int
    safety_violations: int
    mean_decision_latency_ms: float
    p95_decision_latency_ms: float
    mxn_per_hour: float
    mxn_per_km: float | None
    uncompleted_orders: int
    post_accept_infeasible: int
    orders_cancelled: int = 0
    skip_penalties_mxn: float = 0
    cancellation_penalties_mxn: float = 0
    reposition_count: int = 0
    reposition_distance_km: float = 0
    reposition_cost_mxn: float = 0
    net_gain_after_reposition: float = 0
    disruption_caused_lateness: int = 0

    def to_dict(self):
        return asdict(self)


@dataclass
class ShiftResult:
    agent_name: str
    seed: int
    stream_sha256: str
    state: CourierState
    metrics: ShiftMetrics
    log: EventLog
