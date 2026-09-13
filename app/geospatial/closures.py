from dataclasses import dataclass
from datetime import datetime, timedelta
import unicodedata
import re

from app.geospatial.cache import digest
from app.geospatial.geometry import edge_coordinates


def road_key(name):
    text = ''.join(c for c in unicodedata.normalize("NFKD", name.casefold()) if not unicodedata.combining(c))
    text = re.sub(r"\bav\.?\s", "avenida ", text)
    return ' '.join(re.findall(r"\w+", text))


@dataclass(frozen=True)
class ActiveClosure:
    closure_id: str
    start_time: datetime
    end_time: datetime
    blocked_edges: tuple
    road: str | None = None
    zone: int | None = None


class ClosureOverlay:
    def __init__(self, store):
        self.store, self.records = store, {}

    def add(self, closure_id, start_time, duration_min, *, road=None, edges=(), zone=None, transition=None):
        if closure_id in self.records or duration_min <= 0:
            raise ValueError("Duplicate closure ID or nonpositive duration")
        graph, selected = self.store.graph, set(map(tuple, edges))
        if road:
            for u,v,k,data in graph.edges(keys=True, data=True):
                names = data.get("name", [])
                names = names if isinstance(names,list) else [names]
                if any(road_key(n) == road_key(road) for n in names):
                    selected.add((u,v,k))
        if zone is not None:
            # Conservative, deterministic: one inbound directed access edge only.
            access = sorted(graph.in_edges(self.store.node(zone), keys=True))
            if access:
                selected.add(access[0])
        if transition:
            # Only explicit direct edges between the two snapped nodes, never a whole corridor.
            u,v = map(self.store.node, transition)
            selected.update((u,v,k) for k in graph.get_edge_data(u,v,{}))
        if not selected or any(not graph.has_edge(*e) for e in selected):
            raise ValueError("Closure matches no edges or references an unknown edge")
        record = ActiveClosure(closure_id, start_time, start_time + timedelta(minutes=duration_min),
                               tuple(sorted(selected)), road, zone)
        self.records[closure_id] = record
        return record

    def active(self, now):
        return [c for _,c in sorted(self.records.items()) if c.start_time <= now < c.end_time]

    def blocked(self, now):
        return frozenset(e for c in self.active(now) for e in c.blocked_edges)

    def version(self, now):
        return digest(sorted(self.blocked(now)))

    def geojson(self, now):
        return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {
            "type": "MultiLineString", "coordinates": [edge_coordinates(self.store.graph,e) for e in c.blocked_edges]},
            "properties": {"closure_id": c.closure_id, "road": c.road, "zone": c.zone,
                "start_time": c.start_time.isoformat(), "end_time": c.end_time.isoformat(),
                "active": c.start_time <= now < c.end_time, "blocked_edges": c.blocked_edges}}
            for c in self.records.values()]}
