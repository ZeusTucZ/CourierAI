from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.models.requests import DecideRequest
from app.models.responses import DecideResponse, DecisionRecord

router = APIRouter()


@router.post("/decide", response_model=DecideResponse)
async def decide(order: DecideRequest, request: Request):
    try:
        return request.app.state.decisions.decide(order, request.state.started_ns)
    except (OverflowError, ValidationError) as exc:
        # Valid finite scalars can still overflow derived arithmetic/datetimes.
        raise HTTPException(422, "Derived timing or economics exceeds representable bounds") from exc


@router.get("/decisions/{order_id}", response_model=DecisionRecord)
async def explain_decision(order_id: str, request: Request):
    record = request.app.state.decisions.log.get(order_id)
    if record is None:
        raise HTTPException(404, "Decision not found")
    return record
