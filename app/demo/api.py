import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/demo")


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = Field(default=202635, ge=0, le=2**31-1, strict=True)
    shift_hours: int = Field(default=4, ge=1, le=8, strict=True)


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start", "pause", "reset", "speed", "complete"]
    speed: Literal[1, 5, 10, 25] = 25


class Injection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shock_type: Literal["rain", "surge", "closure", "delay"]


def session(request, identifier):
    try:
        return request.app.state.demo.get(identifier)
    except KeyError as exc:
        raise HTTPException(404, "Demo session not found") from exc


@router.post("/simulations", status_code=202)
async def start(body: Start, request: Request):
    try:
        return request.app.state.demo.create(body.seed, body.shift_hours).state()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/simulations/{identifier}")
async def state(identifier: str, request: Request):
    return session(request, identifier).state()


@router.post("/simulations/{identifier}/control")
async def control(identifier: str, body: Control, request: Request):
    session(request, identifier)
    try:
        return request.app.state.demo.control(identifier, body.action, body.speed).state()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/simulations/{identifier}/shocks", status_code=202)
async def inject(identifier: str, body: Injection, request: Request):
    session(request, identifier)
    try:
        return (await request.app.state.demo.inject(identifier, body.shock_type)).state()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/simulations/{identifier}/decisions/{order_id}")
async def decision(identifier: str, order_id: str, request: Request):
    current = session(request, identifier).state()
    order = next((o for o in current["orders"] if o["order_id"] == order_id), None)
    if order is None:
        raise HTTPException(404, "Order has not arrived in this playback")
    return order["decisions"]


@router.websocket("/simulations/{identifier}/ws")
async def updates(websocket: WebSocket, identifier: str):
    await websocket.accept()
    try:
        current = websocket.app.state.demo.get(identifier)
    except KeyError:
        await websocket.close(code=4404, reason="Demo session not found")
        return
    try:
        current.subscribers += 1
        while True:
            state = current.state()
            await websocket.send_json({"type": "simulation_completed" if state["status"] == "completed" else "state", "state": state})
            await asyncio.sleep(.25)
    except (WebSocketDisconnect, RuntimeError, OSError):
        return
    finally:
        current.subscribers -= 1
