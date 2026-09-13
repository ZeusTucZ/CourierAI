"""Single routing worker owns mutable closures. CPU work never occupies the API loop/GIL."""
import asyncio
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from datetime import datetime

_planner = None


def worker(operation, payload, directory):
    global _planner
    from app.geospatial.graph import GraphStore
    from app.geospatial.routing import RoutePlanner
    if _planner is None:
        _planner = RoutePlanner(GraphStore.load(directory))
    now = payload.pop("sim_time", datetime(2000,1,1))
    if operation == "closures":
        return _planner.closures.geojson(now)
    if operation == "closure":
        _planner.closures.add(start_time=now,**payload)
        return _planner.closures.geojson(now)
    if operation == "compare":
        return {algorithm:_planner.route(**payload,algorithm=algorithm,now=now) for algorithm in ("astar","dijkstra")}
    return _planner.route(**payload,now=now)


class RoutingService:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.executor = ProcessPoolExecutor(max_workers=1)

    async def call(self, operation, payload):
        if not (self.directory/"metadata.json").exists():
            raise FileNotFoundError("Run python -m scripts.build_osm_graph before routing")
        return await asyncio.get_running_loop().run_in_executor(self.executor,worker,operation,payload,str(self.directory))

    def close(self):
        self.executor.shutdown(wait=True,cancel_futures=True)
