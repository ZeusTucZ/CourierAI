import csv
import json
from hashlib import sha256
from pathlib import Path
from statistics import mean, median

from app.agents.baseline import GreedyRateBaseline
from app.agents.smart import SmartAgent
from app.logging.event_log import encode_events
from app.models.strategy import StrategySnapshot
from app.simulation.config import ShiftConfig
from app.simulation.generator import generate_shift
from app.simulation.strategic import StrategicSimulator
from app.strategy.models import StrategyPolicy


def seed_sets(tuning=Path("evaluation/tuning_seeds.txt"), heldout=Path("evaluation/heldout_seeds.txt")):
    def read(path):
        seeds = [int(line.strip()) for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if not seeds or len(set(seeds)) != len(seeds):
            raise ValueError("Seed sets must be nonempty with no duplicates")
        return seeds
    train, test = read(tuning), read(heldout)
    if set(train) & set(test):
        raise ValueError("Tuning/heldout overlap")
    return train, test


def validate_training(profile, model, tuning, heldout):
    used = set(profile.training_seeds) | set(model.training_seeds)
    if used & set(heldout) or used - set(tuning):
        raise ValueError("Calibration/model contains unauthorized or heldout seeds")


def fingerprint(*models):
    return sha256(json.dumps([m.model_dump(mode="json") for m in models], sort_keys=True).encode()).hexdigest()


def run_pair_v3(cfg, model, policy, output=None):
    source = generate_shift(cfg)
    snapshot = StrategySnapshot(reservation_wage_mxn_hr=policy.base_reservation_wage, zone_values={})
    results = []
    for agent in (GreedyRateBaseline(snapshot), SmartAgent(snapshot)):
        simulator = StrategicSimulator(cfg, agent, model, policy)
        try:
            result = simulator.run(source)
        except Exception as exc:
            raise RuntimeError(f"FAILED seed={cfg.seed} agent={agent.name} state={simulator.state.summary()} last_events={simulator.log.events[-3:]}: {exc}") from exc
        if output is not None:
            folder = Path(output) / f"seed-{cfg.seed}"
            folder.mkdir(parents=True, exist_ok=True)
            result.log.write(folder / f"{agent.name}.jsonl")
            (folder / f"{agent.name}.trace.jsonl").write_bytes(encode_events(simulator.trace))
            (folder / "source.jsonl").write_bytes(encode_events(source))
        results.append(result)
    return tuple(results)


def enforce_safety(results):
    for result in results:
        if result.metrics.safety_violations:
            raise ValueError(f"FAILED safety seed={result.seed} agent={result.agent_name} state={result.state.summary()}")


def evaluate(seeds, profile, model, policy, *, output, vehicle="moto", hours=8):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frozen = fingerprint(profile, model, policy)
    rows, pairs = [], []
    for seed in seeds:
        cfg = ShiftConfig(seed=seed, shift_hours=hours, vehicle=vehicle, start_location_zone=7, profile=profile)
        baseline, smart = run_pair_v3(cfg, model, policy, output)
        enforce_safety((baseline, smart))
        if fingerprint(profile, model, policy) != frozen:
            raise ValueError("FAILED: experiment configuration mutated")
        b, s = baseline.metrics, smart.metrics
        improvement = (s.net_earnings_mxn - b.net_earnings_mxn) / b.net_earnings_mxn * 100 if b.net_earnings_mxn else None
        rows.append({"seed": seed, "baseline": b.to_dict(), "smart": s.to_dict(), "improvement_pct": improvement})
        pairs.append((baseline, smart))
    percentages = [row["improvement_pct"] for row in rows if row["improvement_pct"] is not None]
    summary = {"status": "PASS", "shifts": len(rows), "frozen_config_sha256": frozen,
        "mean_baseline_net": mean(row["baseline"]["net_earnings_mxn"] for row in rows),
        "mean_smart_net": mean(row["smart"]["net_earnings_mxn"] for row in rows),
        "mean_improvement_pct": mean(percentages) if percentages else None,
        "median_improvement_pct": median(percentages) if percentages else None,
        "undefined_improvements": len(rows) - len(percentages),
        "smart_win_rate_pct": mean(row["smart"]["net_earnings_mxn"] > row["baseline"]["net_earnings_mxn"] for row in rows) * 100,
        "safety_violations": 0, "rows": rows}
    (output / "results.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    (output / "frozen_configuration.json").write_text(json.dumps({"profile": profile.model_dump(mode="json"),
        "model": model.model_dump(mode="json"), "policy": policy.model_dump(mode="json"), "seeds": seeds}, indent=2) + "\n")
    write_results_csv(pairs, output / "results_mvp3.csv")
    return summary


def write_results_csv(pairs, path):
    template = Path("results_table_template.csv")
    header = next(line for line in template.read_text().splitlines() if line.startswith("policy,"))
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header.split(","))
        writer.writeheader()
        for index, name in ((0, "GreedyRate"), (1, "OurAgent")):
            results = [pair[index] for pair in pairs]
            metrics = [r.metrics for r in results]
            # Actual completed pickup-phase distance is logged separately only
            # when available; derive from executed pickup-arrival records.
            pickup = sum([e for e in r.log.events if e["event"] == "earnings_update"][-1]["deadhead_distance_km"] for r in results)
            distance = sum(m.distance_traveled_km for m in metrics)
            offered = sum(m.orders_offered for m in metrics)
            writer.writerow({"policy": name, "mean_earnings_mxn": mean(m.net_earnings_mxn for m in metrics),
                "median_earnings_mxn": median(m.net_earnings_mxn for m in metrics),
                "mean_mxn_per_hr": mean(m.mxn_per_hour for m in metrics),
                "accept_rate_pct": sum(m.orders_accepted for m in metrics) / offered * 100 if offered else 0,
                "orders_completed": sum(m.orders_completed for m in metrics),
                "deadhead_pct_of_km": pickup / distance * 100 if distance else 0,
                "deadline_misses": sum(m.late_deliveries for m in metrics),
                "safety_violations": sum(m.safety_violations for m in metrics)})


ABLATIONS = {"SmartFull": {}, "SmartNoZoneValue": {"use_zone_value": False},
    "SmartNoReposition": {"use_reposition": False}, "SmartNoImprovedBatching": {"use_improved_batching": False},
    "SmartNoHistoricalPrediction": {"use_historical_prediction": False}}


def variant(policy, name):
    return StrategyPolicy.model_validate({**policy.model_dump(), **ABLATIONS[name]})
