import argparse
import json
from pathlib import Path

from app.agents.baseline import GreedyRateBaseline
from app.agents.smart import SmartAgent
from app.logging.event_log import encode_events
from app.metrics.comparison import compare
from app.models.strategy import StrategySnapshot
from app.simulation.config import ShiftConfig, SyntheticConfig
from app.simulation.generator import generate_shift
from app.simulation.simulator import Simulator


def common_arguments(parser: argparse.ArgumentParser):
    parser.add_argument("--shift-hours", type=float, default=8)
    parser.add_argument("--vehicle", choices=("moto", "car", "bike"), default="moto")
    parser.add_argument("--start-zone", type=int, default=7)
    parser.add_argument("--simulation-config", type=Path, help="JSON SyntheticConfig, optional")
    parser.add_argument("--strategy", type=Path, help="JSON StrategySnapshot, optional")
    parser.add_argument("--baseline-threshold", type=float, default=None,
                        help="Defaults to Smart's reservation wage for a controlled comparison")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/mvp2"))


def configuration(args, seed: int):
    settings = SyntheticConfig.model_validate_json(args.simulation_config.read_text(encoding="utf-8")) if args.simulation_config else SyntheticConfig()
    return ShiftConfig(seed=seed, shift_hours=args.shift_hours, vehicle=args.vehicle,
                       start_location_zone=args.start_zone, simulation=settings)


def strategy(args):
    return StrategySnapshot.model_validate_json(args.strategy.read_text(encoding="utf-8")) if args.strategy else StrategySnapshot()


def run_pair(config, snapshot=None, baseline_threshold=None, output_dir=None):
    snapshot = snapshot or StrategySnapshot()
    stream = generate_shift(config)
    baseline = Simulator(config, GreedyRateBaseline(snapshot, baseline_threshold)).run(stream)
    smart = Simulator(config, SmartAgent(snapshot)).run(stream)
    comparison = compare(baseline, smart)
    if output_dir is not None:
        folder = Path(output_dir) / f"{config.vehicle}-seed-{config.seed}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "source.jsonl").write_bytes(encode_events(stream))
        baseline.log.write(folder / "GreedyRateBaseline.jsonl")
        smart.log.write(folder / "SmartAgent.jsonl")
        (folder / "comparison.json").write_text(json.dumps({
            "data_status": "synthetic_uncalibrated_development",
            "shift_config": config.model_dump(mode="json"),
            "stream_sha256": baseline.stream_sha256,
            "GreedyRateBaseline": baseline.metrics.to_dict(), "SmartAgent": smart.metrics.to_dict(),
            "comparison": comparison.to_dict(),
        }, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return baseline, smart, comparison


def print_pair(baseline, smart, comparison):
    print(f"SHIFT {baseline.seed} ({baseline.state.vehicle}) - synthetic development data")
    for result in (baseline, smart):
        metrics = result.metrics
        print(f"\n{result.agent_name}\nNet earnings: MXN {metrics.net_earnings_mxn:.2f}\n"
              f"Completed: {metrics.orders_completed}\nSafety violations: {metrics.safety_violations}\n"
              f"Late deliveries: {metrics.late_deliveries}\nUncompleted orders: {metrics.uncompleted_orders}")
    percentage = "undefined (GreedyRateBaseline net = 0)" if comparison.improvement_pct is None else f"{comparison.improvement_pct:.2f}%"
    print(f"\nNet difference: MXN {comparison.net_earnings_difference_mxn:.2f}\nImprovement: {percentage}")
