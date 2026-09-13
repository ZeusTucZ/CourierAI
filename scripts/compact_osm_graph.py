"""Keep only representative OSM paths needed by the 12-zone demo.

The source graph covers the complete Monterrey bounding box and is useful for
offline evaluation, but it is too large for a 512 MB demo instance.  Keeping
the shortest route for every directed zone pair preserves real street geometry
for all UI routes while making the runtime graph small enough to load quickly.
"""
import argparse
import json
from hashlib import sha256
from pathlib import Path

import networkx as nx
import osmnx as ox

from app.geospatial.graph import DEFAULT_DIR, GraphStore


def compact_graph(directory: Path) -> None:
    directory = Path(directory)
    store = GraphStore.load(directory)
    graph = store.graph
    zone_nodes = list(dict.fromkeys(store.snaps[zone]["node"] for zone in sorted(store.snaps)))
    retained_edges: set[tuple[int, int, int | str]] = set()

    for origin in zone_nodes:
        for destination in zone_nodes:
            if origin == destination:
                continue
            path = nx.shortest_path(graph, origin, destination, weight="travel_time")
            for source, target in zip(path, path[1:]):
                choices = graph.get_edge_data(source, target)
                key = min(choices, key=lambda candidate: float(choices[candidate]["travel_time"]))
                retained_edges.add((source, target, key))

    retained_nodes = {node for edge in retained_edges for node in edge[:2]}
    compact = nx.MultiDiGraph(**graph.graph)
    compact.add_nodes_from((node, dict(graph.nodes[node])) for node in retained_nodes)
    compact.add_edges_from((source, target, key, dict(graph.edges[source, target, key]))
                           for source, target, key in retained_edges)
    compact.graph["demo_graph_scope"] = "shortest OSM paths between representative zones"

    output = directory / "monterrey_drive.graphml"
    temporary = directory / "compacting.graphml"
    ox.save_graphml(compact, temporary)
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    graph_version = sha256(temporary.read_bytes()).hexdigest()
    metadata.update({
        "graph_version": graph_version,
        "node_count": len(compact),
        "edge_count": compact.number_of_edges(),
        "runtime_scope": "representative shortest paths between all configured zones",
    })
    temporary.replace(output)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    snaps_path = directory / "zone_nodes.json"
    snaps = json.loads(snaps_path.read_text(encoding="utf-8"))
    snaps["graph_version"] = graph_version
    snaps_path.write_text(json.dumps(snaps, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact a full OSM graph for the hosted demo")
    parser.add_argument("--directory", default=DEFAULT_DIR)
    compact_graph(Path(parser.parse_args().directory))


if __name__ == "__main__":
    main()
