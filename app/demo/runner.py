"""Build a playback timeline in a separate process using unmodified simulation code."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from app.logging.event_log import encode_events

_store = None
_inputs = None


def run_demo(seed, injections, source=None, shift_hours=4):
    global _store, _inputs
    from app.agents.nearby import FirstNearbyBaselineConfig, FirstNearbyOrderBaseline
    from app.agents.smart import SmartAgent
    from app.evaluation.freeze import load_frozen
    from app.geospatial.graph import GraphStore
    from app.geospatial.routing import RoutePlanner
    from app.geospatial.simulation import GeospatialSimulator
    from app.geospatial.geometry import line, point
    from app.models.strategy import StrategySnapshot
    from app.simulation.config import ShiftConfig
    from app.simulation.generator import generate_shift
    from app.strategy.historical import HistoricalDemandModel
    from app.strategy.models import StrategyPolicy

    if _store is None:
        _store = GraphStore.load()
    if _inputs is None:
        path = Path("artifacts/final_strategy_config.json")
        _inputs = (*load_frozen(path), "Frozen MVP 3 configuration") if path.exists() else (
            None, HistoricalDemandModel(), StrategyPolicy(), "Geographic demo · existing defaults · frozen artifact unavailable")
    profile, model, policy, provenance = _inputs
    cfg = ShiftConfig(seed=seed, shift_hours=shift_hours, vehicle="moto", start_location_zone=7, profile=profile)
    original = source if source is not None else generate_shift(cfg)
    events = deepcopy(original) + deepcopy(injections)
    priority = {"shift_start": 0, "shock": 1, "order_offered": 2, "shift_end": 3}
    events.sort(key=lambda e: (e["sim_time"], priority[e["event"]]))

    class Observer(GeospatialSimulator):
        """Read-only observations at existing public event boundaries."""
        def __init__(self, *args):
            self.frames = []
            super().__init__(*args)

        def _emit(self, name, **fields):
            super()._emit(name, **fields)
            if name not in {"position_update", "earnings_update", "strategy_update", "shift_end"}:
                return
            state = self.state
            route = []
            active_id = self.route[0].order_id if self.route else None
            job = next((j for j in state.in_flight_orders if j.offer.order_id == active_id), None)
            active_orders = []
            for active in state.in_flight_orders:
                next_step = next((step for step in self.route if step.order_id == active.offer.order_id), None)
                active_orders.append({"order_id": active.offer.order_id,
                    "phase": next_step.phase.kind if next_step else "pending",
                    "pickup": point(self.planner.graph, _store.node(active.offer.zone_pickup)),
                    "dropoff": point(self.planner.graph, _store.node(active.offer.zone_dropoff)),
                    "is_current": active.offer.order_id == active_id})
            for step in self.route:
                geo = getattr(step.phase, "geo", None)
                if geo and geo["segments"]:
                    edges = [s["edge"] for s in geo["segments"]]
                    route.append({"order_id": step.order_id, "phase": step.phase.kind,
                        "geometry": line(self.planner.graph, edges, edges[0][0]),
                        "edge_path": edges, "destination_node": geo["destination"],
                        "distance_km": step.phase.distance_km, "eta_min": step.phase.remaining_us / 60_000_000})
            if self.move and hasattr(self.move[1], "geo"):
                geo = self.move[1].geo
                edges = [s["edge"] for s in geo["segments"]]
                route.append({"order_id": None, "phase": "reposition", "geometry": line(self.planner.graph, edges, state.current_node),
                    "edge_path": edges, "destination_node": geo["destination"],
                    "distance_km": self.move[1].distance_km, "eta_min": self.move[1].remaining_us / 60_000_000})
            self.frames.append({"sim_time": state.current_sim_time.isoformat(), "version": len(self.frames),
                "position": point(self.planner.graph, state.current_node), "zone": state.current_zone,
                "status": state.status, "action": fields.get("action"),
                "net_earnings": state.net_earnings, "current_order": active_id,
                "active_orders": active_orders,
                "pickup": point(self.planner.graph, _store.node(job.offer.zone_pickup)) if job else None,
                "dropoff": point(self.planner.graph, _store.node(job.offer.zone_dropoff)) if job else None,
                "target": point(self.planner.graph, _store.node(self.agent.snapshot.target_zone)) if self.agent.snapshot.target_zone else None,
                "routes": route, "completed": state.orders_completed,
                "closures": self.planner.closures.geojson(state.current_sim_time)})

    snapshot = StrategySnapshot(reservation_wage_mxn_hr=policy.base_reservation_wage, zone_values={})
    baseline_config = FirstNearbyBaselineConfig.load()
    agents = {}
    streams = []
    for key, agent in (("baseline", FirstNearbyOrderBaseline(baseline_config, snapshot)), ("smart", SmartAgent(snapshot))):
        settings = policy.model_copy(update={"use_zone_value": False, "use_reposition": False,
            "use_improved_batching": False, "use_historical_prediction": False, "use_cancellation": False}) if key == "baseline" else policy
        simulator = Observer(cfg, agent, model, settings, RoutePlanner(_store, agent.snapshot.vehicle_profiles))
        result = simulator.run(events)
        streams.append(result.stream_sha256)
        decisions = {e["order_id"]: e for e in result.log.events if e["event"] == "decision"}
        offers = {e["order_id"]: e for e in result.log.events if e["event"] == "order_offered"}
        detours = [e for e in simulator.routing_trace if e["type"] == "active_route" and abs(e["detour_minutes"]) > 1e-8]
        agents[key] = {"frames": simulator.frames, "decisions": decisions, "offers": offers,
            "detours": detours, "metrics": result.metrics.to_dict()}
    assert len(set(streams)) == 1, "Agents must consume the identical source stream"
    return {"seed": seed, "shift_hours": shift_hours, "source": original, "stream_hash": streams[0], "same_stream": True,
        "start_time": events[0]["sim_time"], "end_time": events[-1]["sim_time"], "provenance": provenance,
        "orders": [e for e in original if e["event"] == "order_offered"],
        "shocks": [e for e in events if e["event"] == "shock"], "agents": agents,
        "start_position": point(_store.graph, _store.node(cfg.start_location_zone)),
        "baseline_threshold": baseline_config.max_distance_km}
