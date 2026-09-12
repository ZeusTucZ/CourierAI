"""Multi-seed safety and replay audit. Run: python -m scripts.audit_mvp2 --seeds 1 2 3."""
import argparse
from app.metrics.comparison import summarize
from app.simulation.replay import replay_shift
from scripts.shift_common import common_arguments, configuration, run_pair, strategy


def main():
    parser = argparse.ArgumentParser(description="Audit synthetic development seeds")
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    common_arguments(parser)
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("Seeds must be unique")
    snapshot = strategy(args)
    comparisons = []
    replay_failures = []
    safety_errors = []
    print("Synthetic development data; not real-world performance")
    print("Seed | Baseline Net | Smart Net | Improvement | Safety B | Safety S | Replay")
    for seed in args.seeds:
        baseline, smart, comparison = run_pair(configuration(args, seed), snapshot,
                                                args.baseline_threshold, args.output_dir)
        comparisons.append(comparison)
        replays = []
        for result in (baseline, smart):
            path = args.output_dir / f"{result.state.vehicle}-seed-{seed}" / f"{result.agent_name}.jsonl"
            try:
                replay_shift(path)
                replays.append("PASS")
            except Exception as exc:
                replay_failures.append((seed, result.agent_name, str(exc)))
                replays.append("ERROR")
            if result.metrics.safety_violations:
                suspect = next((e for e in result.log.events if e.get("binding_constraint") or e.get("action") == "post_accept_infeasible"), result.log.events[-1])
                safety_errors.append((seed, result.agent_name, result.metrics.safety_violations, suspect))
        percentage = "N/A" if comparison.improvement_pct is None else f"{comparison.improvement_pct:+.2f}%"
        print(f"{seed:4} | {comparison.baseline_net_mxn:12.2f} | {comparison.smart_net_mxn:9.2f} | "
              f"{percentage:11} | {comparison.baseline_safety_violations:8} | "
              f"{comparison.smart_safety_violations:8} | {'/'.join(replays)}")
    summary = summarize(comparisons)
    print(f"\nMean Baseline Net: {summary['mean_baseline_earnings_mxn']:.2f}")
    print(f"Mean Smart Net: {summary['mean_smart_earnings_mxn']:.2f}")
    avg = summary["mean_improvement_pct"]
    print(f"Mean Improvement: {'N/A' if avg is None else f'{avg:+.2f}%'}")
    print(f"Smart Win Rate: {summary['smart_win_rate_pct']:.1f}%")
    print(f"Total Safety Violations: {summary['baseline_safety_violations'] + summary['smart_safety_violations']}")
    print(f"Replay Failures: {len(replay_failures)}")
    print(f"Smart losses: {[c.seed for c in comparisons if c.smart_net_mxn < c.baseline_net_mxn]}")
    for seed, agent, count, event in safety_errors:
        print(f"ERROR safety seed={seed} agent={agent} count={count} event={event}")
    for seed, agent, error in replay_failures:
        print(f"ERROR replay seed={seed} agent={agent}: {error}")
    if safety_errors or replay_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
