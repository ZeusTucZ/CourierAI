"""FastAPI REST and WebSocket endpoints for the MVP 4 simulation demo."""
from typing import Any, Literal
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.demo.manager import simulation_manager

router = APIRouter(prefix="/simulation", tags=["simulation"])


class StartSimulationRequest(BaseModel):
    seed: int = Field(default=30004, description="Demo simulation seed")
    shift_hours: float = Field(default=8.0, ge=1.0, le=24.0)
    vehicle: Literal["moto", "car", "bike"] = Field(default="moto")
    start_location_zone: int = Field(default=7, ge=1, le=12)
    playback_speed: int = Field(default=5, ge=1, le=25)


class SpeedRequest(BaseModel):
    speed: Literal[1, 5, 10, 25] = Field(default=5)


class ShockRequest(BaseModel):
    shock_type: Literal["rain", "surge", "closure", "delay"]
    duration_min: int | None = Field(default=30, ge=5, le=120)
    zone: int | None = Field(default=None, ge=1, le=12)
    multiplier: float | None = Field(default=1.5, gt=0)
    road: str | None = None
    slip_min: int | None = Field(default=15, ge=1, le=60)
    order_id: str | None = None


class SafetyScenarioRequest(BaseModel):
    scenario_type: Literal["vehicle_capacity", "shift_end_infeasible", "mandatory_break", "flagged_zone_night", "heat_rule"]


@router.post("/start")
async def start_simulation(req: StartSimulationRequest):
    return await simulation_manager.start(
        seed=req.seed,
        shift_hours=req.shift_hours,
        vehicle=req.vehicle,
        start_location_zone=req.start_location_zone,
        playback_speed=req.playback_speed,
    )


@router.post("/pause")
async def pause_simulation():
    return await simulation_manager.pause()


@router.post("/resume")
async def resume_simulation():
    return await simulation_manager.resume()


@router.post("/reset")
async def reset_simulation():
    return await simulation_manager.reset()


@router.post("/speed")
async def change_speed(req: SpeedRequest):
    return await simulation_manager.set_speed(req.speed)


@router.post("/shock")
async def inject_shock(req: ShockRequest):
    return await simulation_manager.inject_shock(
        shock_type=req.shock_type,
        duration_min=req.duration_min,
        zone=req.zone,
        multiplier=req.multiplier,
        road=req.road,
        slip_min=req.slip_min,
        order_id=req.order_id,
    )


@router.post("/safety_scenario")
async def trigger_safety(req: SafetyScenarioRequest):
    return await simulation_manager.trigger_safety_scenario(req.scenario_type)


@router.get("/state")
async def get_state():
    return simulation_manager.get_state()


@router.get("/events")
async def get_events():
    return simulation_manager.get_events()


@router.get("/decisions/{order_id}")
async def get_decision_details(order_id: str):
    details = simulation_manager.get_decision(order_id)
    if details is None:
        raise HTTPException(status_code=404, detail=f"Decision for order {order_id} not found in active session")
    return details


@router.get("/results")
async def get_results():
    return simulation_manager.get_results()


@router.get("/historical")
async def get_historical_evaluation():
    return simulation_manager.get_historical()


@router.websocket("/stream")
async def simulation_stream(websocket: WebSocket):
    await simulation_manager.connect_ws(websocket)
    try:
        while True:
            # Keep connection alive; can receive control commands via ws if needed
            message = await websocket.receive_text()
    except WebSocketDisconnect:
        simulation_manager.disconnect_ws(websocket)
