"""Offline route/closure comparison and GeoJSON artifact, not a pytest module."""
import argparse
import json
from pathlib import Path
from time import perf_counter
from datetime import datetime, timedelta

from app.geospatial.graph import GraphStore
from app.geospatial.routing import RoutePlanner, NoRoute


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--origin-zone",type=int,default=7)
    parser.add_argument("--destination-zone",type=int,default=11)
    parser.add_argument("--vehicle",choices=("moto","car","bike"),default="moto")
    parser.add_argument("--block-road")
    parser.add_argument("--block-used-edge",action="store_true")
    parser.add_argument("--offline",action="store_true")
    args=parser.parse_args()
    if args.offline:
        import socket
        def forbidden(*a,**k):
            raise RuntimeError("Network disabled for offline verification")
        socket.socket.connect=forbidden
        socket.create_connection=forbidden
    start=perf_counter()
    planner=RoutePlanner(GraphStore.load())
    report={"cold_graph_and_planner_ms":(perf_counter()-start)*1000}
    now=datetime(2026,3,21,18)
    routes=[]
    for algorithm in ("astar","dijkstra"):
        start=perf_counter()
        route=planner.route(args.origin_zone,args.destination_zone,args.vehicle,algorithm,now=now,use_cache=False)
        report[algorithm+"_ms"]=(perf_counter()-start)*1000
        report[algorithm]={k:route[k] for k in ("distance_km","eta_min","route_hash")}
        routes.append(route)
    normal=routes[0]
    start=perf_counter()
    planner.route(args.origin_zone,args.destination_zone,args.vehicle,now=now)
    report["cached_route_ms"]=(perf_counter()-start)*1000
    report["node_count"]=len(normal["node_path"])
    if args.block_road or args.block_used_edge:
        candidates=[None] if args.block_road else list(reversed(normal["edge_path"][1:-1]))
        for edge in candidates:
            planner.closures.records.clear()
            planner.closures.add("demo",now,10,road=args.block_road,edges=[edge] if edge else ())
            start=perf_counter()
            try:
                rerouted=planner.route(args.origin_zone,args.destination_zone,args.vehicle,now=now)
            except NoRoute:
                if args.block_road:
                    raise
                continue
            report["reroute_ms"]=(perf_counter()-start)*1000
            report["closure"]={"edge":edge,"road":args.block_road,
                "distance_km":rerouted["distance_km"],"eta_min":rerouted["eta_min"],
                "detour_distance_km":rerouted["distance_km"]-normal["distance_km"],
                "detour_minutes":rerouted["eta_min"]-normal["eta_min"]}
            routes.append(rerouted)
            restored=planner.route(args.origin_zone,args.destination_zone,args.vehicle,now=now+timedelta(minutes=10))
            assert restored["node_path"]==normal["node_path"]
            report["expiry_restores_route"]=True
            break
        if "closure" not in report:
            raise RuntimeError("No reroutable used edge found")
    features=[{"type":"Feature","geometry":r["geometry"],"properties":{k:v for k,v in r.items() if k!="geometry"}} for r in routes]
    features+=planner.closures.geojson(now)["features"]
    output=Path("artifacts/geospatial")
    output.mkdir(parents=True,exist_ok=True)
    (output/"osm_route_preview.geojson").write_text(json.dumps({"type":"FeatureCollection","features":features}),encoding="utf-8")
    (output/"route_benchmark.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
