from datetime import datetime, timezone
from typing import Literal
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.geospatial.zones import ZoneRegistry

router = APIRouter()


class TimeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    sim_time: datetime = datetime(2000,1,1)

    @field_validator("sim_time")
    @classmethod
    def utc_naive(cls, value):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


class RouteRequest(TimeRequest):
    origin_zone: int = Field(ge=1,le=12,strict=True)
    destination_zone: int = Field(ge=1,le=12,strict=True)
    vehicle: Literal["moto","car","bike"] = "moto"
    algorithm: Literal["astar","dijkstra"] = "astar"
    rain_factor: float = Field(default=1,ge=1)


class ClosureRequest(TimeRequest):
    closure_id: str = Field(min_length=1,max_length=100)
    duration_min: float = Field(gt=0)
    road: str | None = Field(default=None,min_length=1,max_length=200)
    edges: list[tuple[int,int,int]] = Field(default_factory=list,max_length=10000)
    zone: int | None = Field(default=None,ge=1,le=12)
    transition: tuple[int,int] | None = None

    @model_validator(mode="after")
    def target(self):
        if not (self.road or self.edges or self.zone or self.transition):
            raise ValueError("Provide road, edges, zone or direct zone transition")
        return self


async def dispatch(request, operation, payload):
    try:
        return await request.app.state.routing.call(operation,payload)
    except FileNotFoundError as exc:
        raise HTTPException(503,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.get("/geospatial/zones")
def zones():
    return ZoneRegistry().geojson()


@router.get("/geospatial/graph/status")
def graph_status(request: Request):
    directory=request.app.state.routing.directory
    path=directory/"metadata.json"
    return {"cached":path.exists() and (directory/"monterrey_drive.graphml").exists(),
            "metadata":json.loads(path.read_text(encoding="utf-8")) if path.exists() else None,
            "routing_source_default":"precomputed","download_on_request":False}


@router.post("/routing/route")
async def route(body: RouteRequest,request: Request):
    return await dispatch(request,"route",body.model_dump())


@router.post("/routing/compare")
async def compare(body: RouteRequest,request: Request):
    return await dispatch(request,"compare",body.model_dump(exclude={"algorithm"}))


@router.post("/routing/closures")
async def add_closure(body: ClosureRequest,request: Request):
    return await dispatch(request,"closure",body.model_dump())


@router.get("/routing/closures")
async def closures(request: Request,sim_time: datetime = datetime(2000,1,1)):
    return await dispatch(request,"closures",TimeRequest(sim_time=sim_time).model_dump())


def simulation_data(request, simulation_id):
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",simulation_id):
        raise HTTPException(422,"Invalid simulation ID")
    path=request.app.state.geospatial_runs / simulation_id / "routes.json"
    if not path.is_file():
        raise HTTPException(404,"No saved geographic simulation with this ID")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/simulation/{simulation_id}/routes")
def simulation_routes(simulation_id: str,request: Request):
    return simulation_data(request,simulation_id)


@router.get("/simulation/{simulation_id}/agents/{agent}/route")
def agent_route(simulation_id: str,agent: str,request: Request):
    data=simulation_data(request,simulation_id)
    if agent not in data["agents"]:
        raise HTTPException(404,"Unknown simulation agent")
    return data["agents"][agent]
