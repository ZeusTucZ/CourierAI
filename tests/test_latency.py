import math
from statistics import median
from time import perf_counter_ns

from app.decision.engine import DecisionEngine
from app.models.requests import DecideRequest


def test_engine_has_large_local_budget_margin(payload, snapshot):
    engine = DecisionEngine()
    order = DecideRequest.model_validate(payload)
    samples = []
    for _ in range(300):
        start = perf_counter_ns()
        response = engine.evaluate(order, snapshot).response
        elapsed = (perf_counter_ns() - start) / 1e6
        assert math.isfinite(response.latency_ms)
        assert 0 <= response.latency_ms <= elapsed
        samples.append(elapsed)
    # Median tolerates scheduler pauses; standalone benchmark reports p95/max.
    assert median(samples) < 10, samples
