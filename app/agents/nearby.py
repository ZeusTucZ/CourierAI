"""Myopic proximity baseline; no economics or prediction in the decision path."""
from pathlib import Path
from time import perf_counter_ns
from pydantic import Field
from app.agents.base import decision_request
from app.decision.constraints import evaluate_constraints
from app.decision.timing import build_work_plan
from app.models.common import Model, NonNegative
from app.models.responses import DecideResponse
from app.models.state import resolve_state
from app.models.strategy import StrategySnapshot


class FirstNearbyBaselineConfig(Model):
    version: str = 'first-nearby-v1'
    max_distance_km: NonNegative
    percentile: float = Field(default=75,gt=0,lt=100)
    sample_size: int = Field(default=0,ge=0)
    observed_total_sample_size: int = Field(default=0,ge=0)
    source: str = 'explicit configuration'
    profile_version: str = 'unspecified'
    classification: str = 'configured'
    transformation: str = ''
    limitations: tuple[str,...] = ()
    source_sha256: str | None = None

    @classmethod
    def load(cls,path=Path('config/first_nearby_baseline.json')):
        return cls.model_validate_json(Path(path).read_text())


class FirstNearbyOrderBaseline:
    """Accept the arriving feasible order iff pickup + delivery <= threshold."""
    name = 'FirstNearbyOrderBaseline'

    def __init__(self, config: FirstNearbyBaselineConfig, snapshot=None):
        self.config=config
        self.snapshot=snapshot or StrategySnapshot()

    def decide(self,order,courier_state):
        return self.decide_request(decision_request(order,courier_state))

    def decide_request(self,request):
        start=perf_counter_ns()
        state=resolve_state(request.sim_time,request.courier_state_overrides,self.snapshot.policy.default_shift_hours)
        plan=build_work_plan(request,state,self.snapshot)
        violation=evaluate_constraints(request,state,self.snapshot,plan)
        if violation:
            decision,binding,reason='SKIP',violation.constraint,violation.reason
        else:
            distance=request.distance_pickup_km+request.distance_delivery_km
            accepted=distance<=self.config.max_distance_km
            decision='ACCEPT' if accepted else 'SKIP'
            # The official enum has no distance constraint. Null is permitted;
            # never mislabel this as reservation wage or invent an official enum.
            binding=None
            reason=(f"Accepted: total distance {distance:.6f} km is within the {self.config.max_distance_km:.6f} km nearby-order threshold." if accepted else
                    f"Skipped: total distance {distance:.6f} km exceeds the {self.config.max_distance_km:.6f} km nearby-order threshold.")
        return DecideResponse(order_id=request.order_id,decision=decision,binding_constraint=binding,
                              reason=reason,latency_ms=(perf_counter_ns()-start)/1e6,degraded=self.snapshot.is_stale)
