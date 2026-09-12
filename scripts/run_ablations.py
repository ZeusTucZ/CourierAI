import json
from pathlib import Path

from app.evaluation.runner import ABLATIONS, evaluate, variant
from scripts.mvp3_common import arguments


def main():
    args, profile, model, policy, tuning, _ = arguments("MVP 3 ablations on tuning seeds only")
    from app.evaluation.freeze import load_frozen
    from app.evaluation.runner import validate_training
    profile, model, policy = load_frozen(Path("artifacts/final_strategy_config.json"))
    validate_training(profile, model, tuning, _)
    from app.agents.nearby import FirstNearbyBaselineConfig
    baseline_config = FirstNearbyBaselineConfig.load()
    output = args.output_dir or Path("evaluation/ablation_nearby_results")
    results = {}
    for name in ABLATIONS:
        results[name] = evaluate(tuning, profile, model, variant(policy, name), output=output / name,
                                 vehicle=args.vehicle, hours=args.shift_hours, baseline_config=baseline_config)
    full = results["SmartFull"]["mean_smart_net"]
    rows = [{"variant": name, "mean_net": value["mean_smart_net"], "delta_vs_full": value["mean_smart_net"] - full,
             "delta_vs_baseline": value["mean_smart_net"] - value["mean_baseline_net"]} for name, value in results.items()]
    (output / "ablations.json").write_text(json.dumps(rows, indent=2) + "\n")
    print("Variant | Mean Net | Delta vs Full | Delta vs Baseline")
    for row in rows:
        print(f"{row['variant']} | {row['mean_net']:.2f} | {row['delta_vs_full']:+.2f} | {row['delta_vs_baseline']:+.2f}")


if __name__ == "__main__":
    main()
