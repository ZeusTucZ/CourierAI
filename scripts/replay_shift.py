import argparse
from pathlib import Path

from app.simulation.replay import replay_shift


def main():
    parser = argparse.ArgumentParser(description="Verify recorded decision inputs and full execution replay")
    parser.add_argument("event_log", type=Path)
    args = parser.parse_args()
    try:
        result = replay_shift(args.event_log)
    except (ValueError, KeyError) as exc:
        parser.exit(1, f"FAIL replay: {exc}\n")
    print(f"PASS {result.agent_name}: {result.decisions_checked} decisions; full execution matches")
    print(f"Source SHA256: {result.stream_sha256}")


if __name__ == "__main__":
    main()
