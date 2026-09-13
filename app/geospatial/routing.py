from copy import deepcopy
from datetime import datetime
import math
import networkx as nx
import osmnx as ox

from app.geospatial.cache import RouteCache, digest
from app.geospatial.closures import ClosureOverlay
from app.geospatial.geometry import line, meters, point
from app.models.strategy import StrategySnapshot


class NoRoute(ValueError):
    pass


class RoutePlanner:
    def __init__(self, store, profiles=None):
        self.store, self.graph = store, store.graph
        self.profiles = profiles or StrategySnapshot().vehicle_profiles
        self.closures, self.cache = ClosureOverlay(store), RouteCache()
        # Correct for roundoff/edge length anomalies: guarantees h(u)<=cost(u,v)+h(v).
        self.heuristic_scale = min([1.] + [float(d["length"])/max(meters(point(self.graph,u),point(self.graph,v)),1e-12)
            for u,v,d in self.graph.edges(data=True)]) * (1-1e-9)

    def edge_minutes(self, edge, vehicle):
        data = self.graph.edges[edge]
        speed = min(float(data["speed_kph"]), self.profiles[vehicle].speed_kmh)
        return float(data["length"]) / 1000 / speed * 60

    def route(self, origin_zone, destination_zone, vehicle="moto", algorithm="astar", **kwargs):
        result = self.route_nodes(self.store.node(origin_zone), self.store.node(destination_zone), vehicle, algorithm, **kwargs)
        result["origin"]["zone"] = origin_zone
        result["destination"]["zone"] = destination_zone
        return result

    def route_coordinates(self, origin, destination, vehicle="moto", algorithm="astar", **kwargs):
        for lat,lon in (origin,destination):
            left,bottom,right,top = self.store.zones.document["bbox"]
            if not bottom <= lat <= top or not left <= lon <= right:
                raise ValueError("Coordinates outside graph study bbox")
        nodes, distances = ox.distance.nearest_nodes(self.graph, X=[origin[1],destination[1]], Y=[origin[0],destination[0]], return_dist=True)
        if max(distances)>2000:
            raise ValueError("Coordinates more than 2 km from road access")
        return self.route_nodes(int(nodes[0]),int(nodes[1]),vehicle,algorithm,**kwargs)

    def route_nodes(self, origin, destination, vehicle="moto", algorithm="astar", *, now=None, rain_factor=1, use_cache=True):
        now = now or datetime(2000,1,1)
        if vehicle not in self.profiles or algorithm not in {"astar","dijkstra"}:
            raise ValueError("Unknown vehicle or routing algorithm")
        if not math.isfinite(rain_factor) or rain_factor < 1:
            raise ValueError("Rain factor must be finite and >= 1")
        if origin not in self.graph or destination not in self.graph:
            raise ValueError("Unknown road node")
        blocked = self.closures.blocked(now)
        key = (origin,destination,vehicle,self.store.metadata["graph_version"],self.closures.version(now),
               algorithm,self.profiles[vehicle].speed_kmh)
        result = self.cache.get(key) if use_cache else None
        if result is None:
            def weight(u,v,edges):
                costs = [self.edge_minutes((u,v,k),vehicle) for k in edges if (u,v,k) not in blocked]
                return min(costs) if costs else None
            def heuristic(u,v):
                return self.heuristic_scale * meters(point(self.graph,u),point(self.graph,v)) / 1000 / self.profiles[vehicle].speed_kmh * 60
            try:
                nodes = nx.astar_path(self.graph,origin,destination,heuristic=heuristic,weight=weight) if algorithm == "astar" else nx.dijkstra_path(self.graph,origin,destination,weight=weight)
            except nx.NetworkXNoPath as exc:
                raise NoRoute(f"No open directed route from {origin} to {destination}") from exc
            edges = [(u,v,min((k for k in self.graph[u][v] if (u,v,k) not in blocked),key=lambda k:(self.edge_minutes((u,v,k),vehicle),k))) for u,v in zip(nodes,nodes[1:])]
            distance = sum(float(self.graph.edges[e]["length"]) for e in edges)/1000
            eta = sum(self.edge_minutes(e,vehicle) for e in edges)
            result = {"origin": {"node":origin,"lon":point(self.graph,origin)[0],"lat":point(self.graph,origin)[1]},
                "destination": {"node":destination,"lon":point(self.graph,destination)[0],"lat":point(self.graph,destination)[1]},
                "algorithm":algorithm,"vehicle":vehicle,"distance_km":distance,"base_eta_min":eta,
                "node_path":nodes,"edge_path":[list(e) for e in edges],"geometry":line(self.graph,edges,origin),
                "graph_version":self.store.metadata["graph_version"],"zone_mapping_version":self.store.zones.version,
                "closure_version":self.closures.version(now),"blocked_edges_used":[],
                "route_hash":digest([self.store.metadata["graph_version"],vehicle,edges,distance,eta])}
            self.cache.put(key,result)
        result["rain_factor"], result["eta_min"] = rain_factor, result["base_eta_min"]*rain_factor
        return deepcopy(result)
