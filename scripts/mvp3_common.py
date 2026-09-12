import argparse
import json
from pathlib import Path

from app.calibration.profiles import SimulationProfile
from app.evaluation.runner import evaluate, seed_sets, validate_training
from app.strategy.historical import HistoricalDemandModel
from app.strategy.models import StrategyPolicy


def arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--profile", type=Path, default=Path("artifacts/calibrated_profile.json"))
    parser.add_argument("--model", type=Path, default=Path("artifacts/historical_model.json"))
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--vehicle", choices=("moto", "car", "bike"), default="moto")
    parser.add_argument("--shift-hours", type=float, default=8)
    args = parser.parse_args()
    profile = SimulationProfile.load(args.profile)
    model = HistoricalDemandModel.model_validate_json(args.model.read_text())
    policy = StrategyPolicy.model_validate_json(args.policy.read_text()) if args.policy else StrategyPolicy()
    tuning, heldout = seed_sets()
    validate_training(profile, model, tuning, heldout)
    return args, profile, model, policy, tuning, heldout


def run(mode):
    args, profile, model, policy, tuning, heldout = arguments(f"Frozen MVP 3 {mode} evaluation")
    seeds = heldout if mode == "heldout" else tuning
    if mode == "heldout" and len(seeds) < 10:
        raise ValueError("At least 10 heldout shifts required")
    output = args.output_dir or Path(f"evaluation/{mode}_results")
    try:
        result = evaluate(seeds, profile, model, policy, output=output, vehicle=args.vehicle, hours=args.shift_hours)
    except Exception as exc:
        output.mkdir(parents=True, exist_ok=True)
        (output / "FAILED.json").write_text(json.dumps({"status": "FAILED", "cause": str(exc)}, indent=2) + "\n")
        raise
    print("Seed | Baseline Net | Smart Net | Improvement | Safety B/S")
    for row in result["rows"]:
        pct = "N/A" if row["improvement_pct"] is None else f"{row['improvement_pct']:+.2f}%"
        print(f"{row['seed']} | {row['baseline']['net_earnings_mxn']:.2f} | {row['smart']['net_earnings_mxn']:.2f} | {pct} | 0/0")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    if mode == "heldout":
        Path("artifacts/results_mvp3.csv").write_bytes((output / "results_mvp3.csv").read_bytes())
