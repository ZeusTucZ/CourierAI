"""Local benchmark, separate from correctness tests. No network or disk in decisions."""
import argparse
import json
import math
from statistics import median
from time import perf_counter_ns

from app.decision.engine import DecisionEngine, DecisionService
from app.logging.decision_log import DecisionLog
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.services.strategy_store import StrategyStore
from scripts.capture_responses import demo_offers


def measure(call, orders, iterations):
    for i in range(100):
        call(orders[i % len(orders)])
    samples = []
    for i in range(iterations):
        start = perf_counter_ns()
        call(orders[i % len(orders)])
        samples.append((perf_counter_ns() - start) / 1e6)
    samples.sort()
    return {"iterations": iterations, "median_ms": median(samples),
            "p95_ms": samples[math.ceil(iterations * .95) - 1],
            "max_ms": max(samples), "over_50ms": sum(x > 50 for x in samples)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=5000)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    snapshot = StrategySnapshot()
    engine = DecisionEngine()
    service = DecisionService(StrategyStore(snapshot), DecisionLog())
    orders = [DecideRequest.model_validate(offer) for offer in demo_offers()]
    print(json.dumps({
        "engine": measure(lambda order: engine.evaluate(order, snapshot), orders, args.iterations),
        "service_including_log": measure(service.decide, orders, args.iterations),
    }, indent=2))


if __name__ == "__main__":
    main()
