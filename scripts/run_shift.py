import argparse

from scripts.shift_common import common_arguments, configuration, print_pair, run_pair, strategy


def main():
    parser = argparse.ArgumentParser(description="Run both agents on one identical synthetic shift")
    parser.add_argument("--seed", type=int, required=True)
    common_arguments(parser)
    args = parser.parse_args()
    print_pair(*run_pair(configuration(args, args.seed), strategy(args), args.baseline_threshold, args.output_dir))


if __name__ == "__main__":
    main()
