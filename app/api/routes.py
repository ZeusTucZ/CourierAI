import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.models.requests import DecideRequest
from app.models.responses import DecideResponse, DecisionRecord

router = APIRouter()


@router.post('/strategy/advisory/prewarm')
async def prewarm_advisory(order: DecideRequest, request: Request):
    service = request.app.state.decisions
    advisor = service.advisor
    if advisor is None or not advisor.config.enabled:
        return {'available': False, 'degraded': False, 'advice': None}
    advice = await advisor.prewarm(order, service.strategies.get())
    return {'available': advice is not None, 'degraded': advice is None,
            'advice': advice.model_dump(mode='json') if advice else None,
            'gemini_error': advisor.last_error}


@router.post("/decide", response_model=DecideResponse)
async def decide(order: DecideRequest, request: Request):
    try:
        service = request.app.state.decisions
        response = service.decide(order, request.state.started_ns,
                                  allow_initial_heat_transition=True)
        if service.advisor and service.advisor.config.enabled and service.advisor.config.api_key:
            async def explain_later():
                from app.llm.explanation_service import GeminiExplanationService
                record = service.log.get(order.order_id)
                if record is not None:
                    from app.llm.schemas import StrategyAdvice
                    advice = StrategyAdvice.model_validate(record.gemini_advice) if record.gemini_advice else None
                    explanation = await GeminiExplanationService(service.advisor.client).explain(record, advice)
                    if explanation:
                        service.log.attach_llm_explanation(order.order_id, explanation)
            asyncio.create_task(explain_later())
        return response
    except (OverflowError, ValidationError) as exc:
        # Valid finite scalars can still overflow derived arithmetic/datetimes.
        raise HTTPException(422, "Derived timing or economics exceeds representable bounds") from exc


@router.get("/decisions/{order_id}", response_model=DecisionRecord)
async def explain_decision(order_id: str, request: Request):
    record = request.app.state.decisions.log.get(order_id)
    if record is None:
        raise HTTPException(404, "Decision not found")
    return record


@router.get("/explain_decision/{order_id}", response_model=DecisionRecord,
            include_in_schema=False)
async def explain_decision_probe_compatibility(order_id: str, request: Request):
    """Compatibility alias used by the supplied probe-pack runner."""
    return await explain_decision(order_id, request)
