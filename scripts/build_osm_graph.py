import argparse
import json
from app.geospatial.graph import build_graph, DEFAULT_DIR


def main():
    parser = argparse.ArgumentParser(description="Build and validate cached Monterrey OSM graph")
    parser.add_argument("--rebuild",action="store_true")
    parser.add_argument("--cache-dir",default=DEFAULT_DIR)
    args = parser.parse_args()
    print(json.dumps(build_graph(args.cache_dir,rebuild=args.rebuild).metadata,indent=2))


if __name__ == "__main__":
    main()
