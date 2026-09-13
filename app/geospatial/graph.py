"""Only build_graph accesses OSM. Loading and routing are strictly offline."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import math

import networkx as nx
import osmnx as ox

from app.geospatial.zones import ROOT, ZoneRegistry

DEFAULT_DIR = ROOT / "data/osm"
# Explicit modeling assumptions, not Mexican legal limits or observed traffic.
HWY_SPEEDS = {"motorway": 70, "trunk": 60, "primary": 50, "secondary": 40,
              "tertiary": 35, "residential": 25, "living_street": 15,
              "service": 15, "unclassified": 25}


def build_graph(directory=DEFAULT_DIR, *, rebuild=False):
    directory = Path(directory)
    zones = ZoneRegistry()
    path = directory / "monterrey_drive.graphml"
    if path.exists() and not rebuild:
        return GraphStore.load(directory)
    directory.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = directory / "http_cache"
    ox.settings.requests_timeout = 180
    graph = ox.graph_from_bbox(tuple(zones.document["bbox"]), network_type="drive", retain_all=False)
    graph = ox.routing.add_edge_speeds(graph, hwy_speeds=HWY_SPEEDS, fallback=25)
    graph = ox.routing.add_edge_travel_times(graph)
    temp = directory / "building.graphml"
    ox.save_graphml(graph, temp)
    version = sha256(temp.read_bytes()).hexdigest()
    metadata = {"graph_version": version, "generated_at": datetime.now(timezone.utc).isoformat(),
        "area": "Monterrey metropolitan reference bbox", "bbox": zones.document["bbox"],
        "network_type": "drive", "node_count": len(graph), "edge_count": graph.number_of_edges(),
        "snapping_policy": "nearest node in largest strongly connected component; full graph retained",
        "zone_mapping_version": zones.version, "osmnx_version": ox.__version__,
        "speed_defaults_kmh": HWY_SPEEDS, "attribution": "© OpenStreetMap contributors; ODbL 1.0",
        "source": "https://www.openstreetmap.org/copyright"}
    store = GraphStore(graph, zones, metadata)
    store.validate_connectivity()
    temp.replace(path)
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    store.save_snaps(directory)
    return store


class GraphStore:
    def __init__(self, graph, zones, metadata, snaps=None):
        self.zones, self.metadata = zones, metadata
        # Sorted insertion order makes NetworkX tie behavior reproducible after reload.
        ordered = nx.MultiDiGraph(**graph.graph)
        ordered.add_nodes_from(sorted(graph.nodes(data=True)))
        ordered.add_edges_from(sorted(graph.edges(keys=True, data=True), key=lambda e: e[:3]))
        for _, _, _, data in ordered.edges(keys=True, data=True):
            if not math.isfinite(float(data["length"])) or float(data["length"]) < 0:
                raise ValueError("Invalid OSM edge length")
            if not math.isfinite(float(data["speed_kph"])) or float(data["speed_kph"]) <= 0:
                raise ValueError("Invalid OSM edge speed")
        self.graph = nx.freeze(ordered)
        if snaps is None:
            records = list(zones.zones.values())
            backbone = ordered.subgraph(max(nx.strongly_connected_components(ordered),key=len))
            nodes, distances = ox.distance.nearest_nodes(backbone, X=[z["longitude"] for z in records],
                Y=[z["latitude"] for z in records], return_dist=True)
            snaps = {z["zone_id"]: {"node": int(n), "distance_m": float(d)} for z,n,d in zip(records,nodes,distances)}
        self.snaps = snaps
        if set(snaps) != set(zones.zones) or any(s["node"] not in ordered or s["distance_m"] > 2000 for s in snaps.values()):
            raise ValueError("Missing zone snap or road access farther than 2 km")

    @classmethod
    def load(cls, directory=DEFAULT_DIR):
        directory = Path(directory)
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        path = directory / "monterrey_drive.graphml"
        if sha256(path.read_bytes()).hexdigest() != metadata["graph_version"]:
            raise ValueError("Graph checksum mismatch; rebuild cache")
        zones = ZoneRegistry()
        if zones.version != metadata["zone_mapping_version"]:
            raise ValueError("Zone mapping changed; rebuild graph/snaps explicitly")
        saved = json.loads((directory / "zone_nodes.json").read_text(encoding="utf-8"))
        if (saved["graph_version"], saved["zone_mapping_version"]) != (metadata["graph_version"], zones.version):
            raise ValueError("Stale node cache")
        return cls(ox.load_graphml(path), zones, metadata, {int(k):v for k,v in saved["snaps"].items()})

    def save_snaps(self, directory):
        data = {"graph_version": self.metadata["graph_version"], "zone_mapping_version": self.zones.version, "snaps": self.snaps}
        (Path(directory) / "zone_nodes.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    def validate_connectivity(self):
        nodes = {s["node"] for s in self.snaps.values()}
        if not any(nodes <= component for component in nx.strongly_connected_components(self.graph)):
            raise ValueError("Zone access nodes are not mutually reachable in the directed graph")

    def node(self, zone):
        if zone not in self.snaps:
            raise ValueError(f"Unknown zone {zone}")
        return self.snaps[zone]["node"]
