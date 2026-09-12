"""Local HTTP handler, offline updater, bounded insertion, and shift timings."""
import argparse
import json
from datetime import datetime, timedelta
from math import ceil
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from fastapi.testclient import TestClient

from app.agents.base import decision_request
from app.calibration.profiles import SimulationProfile
from app.evaluation.runner import run_pair_v3
from app.main import create_app
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.services.strategy_store import StrategyStore
from app.simulation.config import ShiftConfig
from app.simulation.state import ActiveOrder, CourierState
from app.strategy.historical import HistoricalDemandModel
from app.strategy.models import StrategyPolicy
from app.strategy.routing import insert_order, steps_for
from app.strategy.updater import StrategyUpdater
from validate_format import PROBE


def measure(callback, iterations):
    for _ in range(20):
        callback()
    times = []
    for _ in range(iterations):
        start = perf_counter_ns()
        callback()
        times.append((perf_counter_ns() - start) / 1e6)
    times.sort()
    return {"n": iterations, "median_ms": median(times), "p95_ms": times[ceil(.95 * iterations) - 1],
            "max_ms": times[-1], "over_50ms": sum(t > 50 for t in times)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1000)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("Iterations must be positive")
    profile = SimulationProfile.load(Path("artifacts/calibrated_profile.json"))
    model = HistoricalDemandModel.model_validate_json(Path("artifacts/historical_model.json").read_text())
    from app.evaluation.freeze import load_frozen
    profile, model, policy = load_frozen(Path("artifacts/final_strategy_config.json"))
    store = StrategyStore(StrategySnapshot())
    updater = StrategyUpdater(model, policy, range(1, 13))
    when = datetime(2026, 3, 21, 18)
    snapshot = updater.update(store, when, "moto", 300)
    with TestClient(create_app(snapshot)) as client:
        def decide():
            response = client.post("/decide", json=PROBE)
            if response.status_code != 200:
                raise RuntimeError(response.text)
        http = measure(decide, args.iterations)
    update = measure(lambda: updater.update(store, when, "moto", 300), args.iterations)
    cfg = ShiftConfig(seed=1, shift_hours=8, vehicle="moto", start_location_zone=7)
    state = CourierState.for_shift(cfg)
    request = DecideRequest.model_validate({**PROBE, "sim_time": state.current_sim_time,
        "estimated_pickup_min": 2, "estimated_delivery_min": 3, "restaurant_prep_min": 0,
        "zone_dropoff": 7, "weight_kg": 1, "volume_liters": 1})
    route = []
    for index in range(3):
        job = ActiveOrder.accepted(request.model_copy(update={"order_id": f"ACTIVE-{index}"}), snapshot,
                                   state.current_sim_time + timedelta(hours=1))
        state.in_flight_orders.append(job)
        route.extend(steps_for(job))
    candidate = ActiveOrder.accepted(request, snapshot, state.current_sim_time + timedelta(hours=1))
    insertion = measure(lambda: insert_order(route, candidate, state.in_flight_orders,
        decision_request(request, state), snapshot, policy), args.iterations)
    shift_start = perf_counter_ns()
    for seed in (1, 2, 3):
        run_pair_v3(cfg.model_copy(update={"seed": seed, "profile": profile}), model, policy)
    shifts = {"agent_shifts": 6, "total_ms": (perf_counter_ns() - shift_start) / 1e6}
    report = {"decide_http_in_process": http, "strategy_update": update, "batch_insertion_3_active": insertion,
              "full_shifts": shifts, "measurement": "TestClient HTTP stack, not network round trip; real measured timings"}
    Path("artifacts/benchmark_mvp3.json").write_text(json.dumps(report, indent=2) + "\n")
    Path("artifacts/strategy_snapshot.json").write_text(snapshot.model_dump_json(indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if http["p95_ms"] >= 50 or insertion["p95_ms"] >= 50:
        raise SystemExit("FAILED fast path or insertion latency budget")


if __name__ == "__main__":
    main()
