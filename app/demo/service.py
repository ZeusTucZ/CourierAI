"""Session clock and deterministic playback. Injection branches only unshown future events."""
import asyncio
from bisect import bisect_right
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from time import monotonic
from uuid import uuid4

from app.demo.runner import run_demo


class DemoSession:
    def __init__(self, seed, shift_hours=4, vehicle="moto"):
        self.id, self.seed, self.shift_hours, self.vehicle = uuid4().hex, seed, shift_hours, vehicle
        self.data = None
        self.status, self.error = "preparing", None
        self.speed, self.offset, self.anchor = 25, 0., monotonic()
        self.injections, self.version = [], 0
        self.explanations = {}
        self.explanation_tasks = {}
        self.task = None
        self.subscribers = 0
        self.last_access = monotonic()
        self.rewound = False

    def seconds(self):
        current = self.offset + (monotonic() - self.anchor) * self.speed if self.status == "running" else self.offset
        if self.data:
            length = (datetime.fromisoformat(self.data["end_time"]) - datetime.fromisoformat(self.data["start_time"])).total_seconds()
            if current >= length:
                self.offset, self.status = length, "completed"
            return min(current, length)
        return current

    def pause(self):
        self.offset = self.seconds()
        if self.status == "running":
            self.status = "paused"

    def state(self):
        elapsed = self.seconds()
        self.last_access = monotonic()
        base = {"id": self.id, "seed": self.seed, "shift_hours": self.shift_hours, "vehicle": self.vehicle, "status": self.status, "speed": self.speed,
                "error": self.error, "revision": self.version}
        if not self.data:
            return {**base, "agents": {}, "orders": [], "shocks": [], "same_stream": False}
        at = (datetime.fromisoformat(self.data["start_time"]) + timedelta(seconds=elapsed)).isoformat()
        visible_at = (datetime.fromisoformat(self.data["start_time"]) - timedelta(microseconds=1)).isoformat() if self.rewound else at
        agents = {}
        for key, data in self.data["agents"].items():
            index = bisect_right([f["sim_time"] for f in data["frames"]], visible_at) - 1
            frame = data["frames"][index] if index >= 0 else {"version": -1,
                "position": self.data["start_position"], "zone": 7, "status": "idle", "action": None,
                "net_earnings": 0, "current_order": None, "routes": [], "pickup": None,
                "dropoff": None, "active_orders": [], "target": None, "completed": 0,
                "closures": {"type": "FeatureCollection", "features": []}}
            # Closures can expire between position events. Filter by the playback clock.
            closures = {**frame["closures"], "features": [f for f in frame["closures"]["features"]
                if f["properties"]["start_time"] <= at < f["properties"]["end_time"]]}
            agents[key] = {**frame, "closures": closures}
        orders = []
        for order in self.data["orders"]:
            if order["sim_time"] > visible_at:
                continue
            orders.append({"order_id": order["order_id"], "sim_time": order["sim_time"],
                "zone_pickup": order["zone_pickup"], "zone_dropoff": order["zone_dropoff"],
                "decisions": {key: self.data["agents"][key]["decisions"].get(order["order_id"]) for key in agents},
                "offers": {key: self.data["agents"][key]["offers"].get(order["order_id"]) for key in agents}})
        shocks = []
        for index, shock in enumerate(self.data["shocks"]):
            if shock["sim_time"] <= visible_at:
                detours = {key: [{"order_id": e["order_id"], "detour_distance_km": e["detour_distance_km"],
                    "detour_minutes": e["detour_minutes"]} for e in self.data["agents"][key]["detours"]
                    if e["sim_time"] == shock["sim_time"]] for key in agents}
                shocks.append({**shock, "id": f"shock-{index}", "detours": detours})
        return {**base, "status": self.status, "sim_time": at, "elapsed_seconds": elapsed,
            "start_time": self.data["start_time"], "end_time": self.data["end_time"],
            "same_stream": self.data["same_stream"], "provenance": self.data["provenance"],
            "baseline_threshold": self.data["baseline_threshold"], "agents": agents, "orders": orders,
            "shocks": shocks, "metrics": {key: d["metrics"] for key, d in self.data["agents"].items()} if self.status == "completed" else None}


class DemoService:
    def __init__(self, runner=run_demo):
        self.sessions, self.runner = {}, runner
        self.executor = ProcessPoolExecutor(max_workers=1) if runner is run_demo else None

    async def compute(self, seed, injections, source=None, shift_hours=4, vehicle="moto"):
        if self.executor:
            return await asyncio.get_running_loop().run_in_executor(self.executor, self.runner, seed, injections, source, shift_hours, vehicle)
        return self.runner(seed, injections, source, shift_hours, vehicle)

    def create(self, seed, shift_hours=4, vehicle="moto"):
        for key, session in list(self.sessions.items()):
            if (monotonic() - session.last_access > 3600 and session.subscribers == 0
                    and not (session.task and not session.task.done())):
                del self.sessions[key]
        if len(self.sessions) >= 8:
            candidates = [session for session in self.sessions.values()
                if session.subscribers == 0 and not (session.task and not session.task.done())]
            if not candidates:
                raise ValueError("Eight demo sessions are currently active; close an older demo tab before starting another")
            oldest = min(candidates, key=lambda session: session.last_access)
            del self.sessions[oldest.id]
        session = DemoSession(seed, shift_hours, vehicle)
        self.sessions[session.id] = session
        session.task = asyncio.create_task(self.prepare(session))
        return session

    async def prepare(self, session):
        try:
            session.data = await self.compute(session.seed, [], shift_hours=session.shift_hours, vehicle=session.vehicle)
            session.status, session.anchor = "running", monotonic()
        except Exception as exc:
            session.status, session.error = "error", str(exc)

    def get(self, identifier):
        if identifier not in self.sessions:
            raise KeyError("Demo session not found")
        return self.sessions[identifier]

    def control(self, identifier, action, speed=None):
        session = self.get(identifier)
        if session.status in {"preparing", "updating", "error"}:
            raise ValueError("Wait for simulation preparation or create a new session after an error")
        was_running = session.status == "running"
        session.pause()
        if action == "reset":
            # Rewind the exact same source and injection schedule, without recalculation.
            session.offset, session.status = 0., "paused"
            session.rewound = True
        elif action == "complete":
            length = (datetime.fromisoformat(session.data["end_time"]) - datetime.fromisoformat(session.data["start_time"])).total_seconds()
            session.offset, session.status, session.rewound = length, "completed", False
        elif action == "start" and session.status != "completed":
            session.status = "running"
            session.rewound = False
        elif action == "speed":
            session.speed = speed
            if was_running:
                session.status = "running"
        session.anchor = monotonic()
        return session

    async def inject(self, identifier, kind):
        session = self.get(identifier)
        if session.status not in {"running", "paused"}:
            raise ValueError("Start a turn before injecting an event")
        resume = session.status == "running"
        session.pause()
        state = session.state()
        # New event strictly follows every state already shown, even at equal timestamps.
        when = datetime.fromisoformat(state["sim_time"]) + timedelta(microseconds=1)
        if when >= datetime.fromisoformat(session.data["end_time"]):
            raise ValueError("The shift has ended")
        event = {"event": "shock", "sim_time": when.isoformat(), "shock_type": kind}
        if kind == "delay":
            order_id = state["agents"]["smart"]["current_order"] or state["agents"]["baseline"]["current_order"]
            if not order_id:
                raise ValueError("Delay requires an active order")
            event.update(order_id=order_id, slip_min=5)
        elif kind == "surge":
            event.update(zone=state["agents"]["smart"]["zone"], multiplier=1.5, duration_min=10)
        elif kind == "rain":
            event.update(duration_min=10)
        elif kind == "closure":
            routes = state["agents"]["smart"]["routes"] or state["agents"]["baseline"]["routes"]
            # A future edge, not the currently occupied first edge. No route solving here.
            edges = [e for r in routes for e in r["edge_path"]][1:]
            if not edges:
                raise ValueError("Road closure requires an active route with an upcoming edge")
            edge = edges[len(edges) // 2]
            event.update(road="edge:" + ":".join(map(str, edge)), duration_min=10)
        else:
            raise ValueError("Unknown shock")
        session.status, session.error = "updating", None

        async def rebuild():
            try:
                revised = await self.compute(session.seed, session.injections + [event], session.data["source"], session.shift_hours, session.vehicle)
                # The past must not change when branching at the presentation cursor.
                from app.simulation.replay import logical
                for key in ("baseline", "smart"):
                    for oid, decision in session.data["agents"][key]["decisions"].items():
                        if decision["sim_time"] < event["sim_time"]:
                            if logical(decision) != logical(revised["agents"][key]["decisions"].get(oid)):
                                raise ValueError("Injection changed an already displayed decision")
                session.data = revised
                session.injections.append(event)
                session.version += 1
                session.offset += .000001
            except Exception as exc:
                session.error = str(exc)
            finally:
                session.status = "running" if resume else "paused"
                session.anchor = monotonic()
        session.task = asyncio.create_task(rebuild())
        return session

    async def close(self):
        tasks = [s.task for s in self.sessions.values() if s.task and not s.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
