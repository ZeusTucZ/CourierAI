import argparse
import json
from pathlib import Path

from app.metrics.comparison import summarize
from scripts.shift_common import common_arguments, configuration, run_pair, strategy


def read_seed_file(path: Path) -> list[int]:
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def main():
    parser = argparse.ArgumentParser(description="Development comparison; no automatic reporting-seed runs")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--seeds", type=int, nargs="+")
    source.add_argument("--seed-file", type=Path)
    common_arguments(parser)
    args = parser.parse_args()
    seeds = args.seeds if args.seeds is not None else read_seed_file(args.seed_file)
    if not seeds or len(set(seeds)) != len(seeds):
        parser.error("Supply at least one seed, without duplicates")
    snapshot = strategy(args)
    comparisons = []
    print("Synthetic development data - not real-world performance")
    print("Seed | GreedyRateBaseline MXN | SmartAgent MXN | Improvement %")
    for seed in seeds:
        _, _, result = run_pair(configuration(args, seed), snapshot, args.baseline_threshold, args.output_dir)
        comparisons.append(result)
        percentage = "N/A" if result.improvement_pct is None else f"{result.improvement_pct:.2f}"
        print(f"{seed} | {result.baseline_net_mxn:.2f} | {result.smart_net_mxn:.2f} | {percentage}")
    summary = summarize(comparisons)
    print(json.dumps(summary, indent=2))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "multi_seed_comparison.json").write_text(json.dumps({
        "data_status": "synthetic_uncalibrated_development", "summary": summary,
        "comparisons": [item.to_dict() for item in comparisons],
    }, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
