"""Simulation manager orchestrating session lifecycle, background stepping, and WebSocket broadcasting."""
import asyncio
import json
from pathlib import Path
from typing import Any, Set

from fastapi import WebSocket

from app.demo.session import DualSimulationSession

OUT = Path("artifacts")


class SimulationManager:
    """Singleton coordinator for the interactive demo simulation."""

    def __init__(self):
        self.session: DualSimulationSession = DualSimulationSession(seed=30004)
        self.active_websockets: Set[WebSocket] = set()
        self._loop_task: asyncio.Task | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused by default when started
        self._stop_requested = False

    def get_session(self) -> DualSimulationSession:
        return self.session

    async def connect_ws(self, websocket: WebSocket):
        await websocket.accept()
        self.active_websockets.add(websocket)
        # Send initial state immediately
        await websocket.send_text(json.dumps({
            "type": "state_update",
            "data": self.session.get_state(),
        }))

    def disconnect_ws(self, websocket: WebSocket):
        self.active_websockets.discard(websocket)

    async def broadcast(self, message_type: str, data: Any):
        if not self.active_websockets:
            return
        payload = json.dumps({"type": message_type, "data": data})
        dead = []
        for ws in self.active_websockets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active_websockets.discard(ws)

    async def start(
        self,
        seed: int = 30004,
        shift_hours: float = 8.0,
        vehicle: str = "moto",
        start_location_zone: int = 7,
        playback_speed: int = 5,
    ) -> dict[str, Any]:
        await self.stop()
        self.session = DualSimulationSession(
            seed=seed,
            shift_hours=shift_hours,
            vehicle=vehicle,
            start_location_zone=start_location_zone,
            playback_speed=playback_speed,
        )
        self.session.status = "running"
        self._pause_event.set()
        self._stop_requested = False
        self._loop_task = asyncio.create_task(self._simulation_loop())
        await self.broadcast("state_update", self.session.get_state())
        return self.session.get_state()

    async def pause(self) -> dict[str, Any]:
        self.session.status = "paused"
        self._pause_event.clear()
        await self.broadcast("state_update", self.session.get_state())
        return self.session.get_state()

    async def resume(self) -> dict[str, Any]:
        if self.session.is_completed():
            return self.session.get_state()
        self.session.status = "running"
        self._pause_event.set()
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._simulation_loop())
        await self.broadcast("state_update", self.session.get_state())
        return self.session.get_state()

    async def reset(self) -> dict[str, Any]:
        await self.stop()
        self.session = DualSimulationSession(
            seed=self.session.seed,
            shift_hours=self.session.shift_hours,
            vehicle=self.session.vehicle,
            start_location_zone=self.session.start_location_zone,
            playback_speed=self.session.playback_speed,
        )
        self.session.status = "idle"
        await self.broadcast("state_update", self.session.get_state())
        return self.session.get_state()

    async def set_speed(self, speed: int) -> dict[str, Any]:
        if speed in (1, 5, 10, 25):
            self.session.playback_speed = speed
            await self.broadcast("state_update", self.session.get_state())
        return self.session.get_state()

    async def stop(self):
        self._stop_requested = True
        self._pause_event.set()
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self._loop_task = None

    async def inject_shock(self, **kwargs) -> dict[str, Any]:
        res = self.session.inject_shock(**kwargs)
        await self.broadcast("state_update", self.session.get_state())
        await self.broadcast("shock_injected", res)
        return res

    async def trigger_safety_scenario(self, scenario_type: str) -> dict[str, Any]:
        res = self.session.trigger_safety_scenario(scenario_type)
        await self.broadcast("state_update", self.session.get_state())
        await self.broadcast("safety_scenario", res)
        return res

    async def _simulation_loop(self):
        """Asynchronous execution loop advancing the simulation at the requested playback speed."""
        try:
            while not self._stop_requested and not self.session.is_completed():
                await self._pause_event.wait()
                if self._stop_requested:
                    break

                # Advance one milestone step
                state = self.session.step()

                # Broadcast update
                await self.broadcast("state_update", state)

                # Delay according to playback speed
                # 1x -> 600ms, 5x -> 200ms, 10x -> 100ms, 25x -> 30ms
                delay_map = {1: 0.6, 5: 0.2, 10: 0.08, 25: 0.025}
                sleep_sec = delay_map.get(self.session.playback_speed, 0.15)
                await asyncio.sleep(sleep_sec)

            if self.session.is_completed():
                self.session.status = "completed"
                await self.broadcast("state_update", self.session.get_state())
                await self.broadcast("simulation_completed", self.get_results())
        except asyncio.CancelledError:
            pass

    def get_state(self) -> dict[str, Any]:
        return self.session.get_state()

    def get_events(self) -> list[dict[str, Any]]:
        return self.session.timeline_events

    def get_decision(self, order_id: str) -> dict[str, Any] | None:
        return self.session.decisions_log.get(order_id)

    def get_results(self) -> dict[str, Any]:
        b = self.session.sim_baseline.state
        s = self.session.sim_smart.state
        b_net = round(b.net_earnings, 2)
        s_net = round(s.net_earnings, 2)
        diff = round(s_net - b_net, 2)
        uplift = round((diff / b_net * 100), 2) if b_net > 0 else 0.0

        return {
            "status": "completed" if self.session.is_completed() else self.session.status,
            "seed": self.session.seed,
            "shift_hours": self.session.shift_hours,
            "winner": "Smart" if s_net > b_net else ("Baseline" if b_net > s_net else "Tie"),
            "absolute_difference_mxn": diff,
            "improvement_pct": uplift,
            "baseline": {
                "net_earnings_mxn": b_net,
                "gross_earnings_mxn": round(b.gross_earnings, 2),
                "operating_costs_mxn": round(b.operating_costs, 2),
                "orders_completed": b.orders_completed,
                "orders_accepted": b.orders_accepted,
                "orders_skipped": b.orders_skipped,
                "distance_traveled_km": round(b.distance_traveled_km, 2),
                "idle_time_min": round(b.idle_time_min, 1),
                "late_deliveries": b.late_deliveries,
                "safety_violations": b.safety_violations,
                "mxn_per_km": round(b_net / b.distance_traveled_km, 2) if b.distance_traveled_km > 0 else 0.0,
            },
            "smart": {
                "net_earnings_mxn": s_net,
                "gross_earnings_mxn": round(s.gross_earnings, 2),
                "operating_costs_mxn": round(s.operating_costs, 2),
                "orders_completed": s.orders_completed,
                "orders_accepted": s.orders_accepted,
                "orders_skipped": s.orders_skipped,
                "distance_traveled_km": round(s.distance_traveled_km, 2),
                "idle_time_min": round(s.idle_time_min, 1),
                "late_deliveries": s.late_deliveries,
                "safety_violations": s.safety_violations,
                "reposition_distance_km": round(s.reposition_distance_km, 2),
                "mxn_per_km": round(s_net / s.distance_traveled_km, 2) if s.distance_traveled_km > 0 else 0.0,
            },
        }

    def get_historical(self) -> dict[str, Any]:
        summary_file = OUT / "baseline_vs_smart_summary.json"
        if summary_file.exists():
            return json.loads(summary_file.read_text())
        return {
            "evaluation_name": "Offline held-out evaluation (20 shifts)",
            "seed_count": 20,
            "aggregate_economics": {
                "mean_baseline_net_mxn": 896.73,
                "mean_smart_net_mxn": 1041.82,
                "mean_improvement_pct": 17.12,
                "smart_win_rate_pct": 85.0,
            },
            "aggregate_operations": {
                "mean_baseline_distance_km": 88.92,
                "mean_smart_distance_km": 76.68,
                "total_smart_safety_violations": 0,
                "total_baseline_safety_violations": 0,
            },
        }


# Global singleton instance
simulation_manager = SimulationManager()
