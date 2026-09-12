import argparse
import json
from time import perf_counter

from scripts.shift_common import common_arguments, configuration, run_pair, strategy


def main():
    parser = argparse.ArgumentParser(description="Accelerated synthetic shift runtime benchmark")
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    common_arguments(parser)
    args = parser.parse_args()
    snapshot = strategy(args)
    start = perf_counter()
    pairs = [run_pair(configuration(args, seed), snapshot, args.baseline_threshold) for seed in args.seeds]
    elapsed = perf_counter() - start
    print(json.dumps({"pairs": len(pairs), "agent_shifts": len(pairs) * 2,
        "elapsed_seconds": elapsed, "seconds_per_pair": elapsed / len(pairs),
        "max_p95_decision_latency_ms": max(result.metrics.p95_decision_latency_ms for pair in pairs for result in pair[:2]),
        "total_safety_violations": sum(result.metrics.safety_violations for pair in pairs for result in pair[:2]),
    }, indent=2))


if __name__ == "__main__":
    main()
