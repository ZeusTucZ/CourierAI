import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agents.smart import SmartAgentNoLLM, SmartAgentWithGemini
from app.llm.fallback import adjustment
from app.llm.gemini_client import GeminiConfig
from app.llm.schemas import StrategyAdvice
from app.llm.strategy_advisor import GeminiStrategyAdvisor, observable_context
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot

ADVICE = StrategyAdvice(recommendation='ACCEPT', confidence=1, demand_outlook='HIGH',
    destination_quality='GOOD', opportunity_risk='LOW', key_factors=['historical demand'],
    explanation='Historical demand is high.')

class FakeClient:
    def __init__(self, value=ADVICE):
        self.value = value
        self.calls = []
    async def analyze(self, payload):
        self.calls.append(payload)
        if isinstance(self.value, Exception):
            raise self.value
        return self.value

def setup(payload, client=None, **config_overrides):
    config = GeminiConfig(enabled=True, api_key='fake', **config_overrides)
    fake = client or FakeClient()
    advisor = GeminiStrategyAdvisor(fake, config)
    agent = SmartAgentWithGemini(StrategySnapshot(), advisor)
    order = DecideRequest.model_validate(payload)
    return agent, advisor, fake, order

def test_schema_and_bounded_translation():
    assert adjustment(ADVICE) == 20
    assert adjustment(ADVICE, -4, 4) == 4
    assert adjustment(ADVICE.model_copy(update={'recommendation': 'NEUTRAL'})) == 0
    assert adjustment(ADVICE) == adjustment(ADVICE)
    with pytest.raises(ValidationError):
        StrategyAdvice.model_validate({**ADVICE.model_dump(), 'confidence': 2})
    with pytest.raises(ValidationError):
        StrategyAdvice.model_validate_json('{bad json')

def test_cache_ttl_and_fallback(payload):
    agent, advisor, fake, order = setup(payload)
    assert asyncio.run(advisor.prewarm(order, agent.snapshot)) == ADVICE
    assert len(fake.calls) == 1
    assert asyncio.run(advisor.prewarm(order, agent.snapshot)) == ADVICE
    assert len(fake.calls) == 1
    result = agent.decide_request(order)
    assert result.gemini_cache_hit and result.llm_adjustment_mxn_hr == 20
    assert result.post_llm_adjusted_rate == result.pre_llm_adjusted_rate + 20
    later = order.model_copy(update={'sim_time': order.sim_time + timedelta(minutes=11)})
    assert advisor.get(observable_context(later, agent.snapshot), agent.snapshot.version) is None
    fake.value = TimeoutError()
    assert asyncio.run(advisor.prewarm(later, agent.snapshot)) is None
    assert advisor.failures == advisor.timeouts == 1
    assert agent.decide_request(later).degraded

def test_disabled_and_missing_key(payload):
    order = DecideRequest.model_validate(payload)
    assert SmartAgentNoLLM().decide_request(order).llm_adjustment_mxn_hr == 0
    config = GeminiConfig(enabled=True, api_key=None)
    advisor = GeminiStrategyAdvisor(FakeClient(), config)
    agent = SmartAgentWithGemini(advisor=advisor)
    assert asyncio.run(advisor.prewarm(order, agent.snapshot)) is None
    result = agent.decide_request(order)
    assert result.degraded and result.llm_adjustment_mxn_hr == 0

def test_safety_and_trace(payload):
    agent, advisor, _, order = setup({**payload, 'zone_dropoff': 11, 'sim_time': '2026-03-21T22:00:00'})
    asyncio.run(advisor.prewarm(order, agent.snapshot))
    response = agent.decide_request(order)
    assert response.decision == 'SKIP'
    assert response.binding_constraint == 'flagged_zone_night'
    assert response.llm_adjustment_mxn_hr == 0
    record = agent.service.log.get(order.order_id)
    assert record.structured_reason == response.reason
    assert record.gemini_advice['recommendation'] == 'ACCEPT'

def test_no_future_leakage(payload):
    order = DecideRequest.model_validate(payload)
    snapshot = StrategySnapshot()
    left = observable_context(order, snapshot)
    right = observable_context(order, snapshot)
    assert left == right
    assert 'future' not in str(left).lower() and 'seed' not in str(left).lower()
    assert 'next_orders' not in str(left)

def test_changed_decision_and_metrics(payload):
    order = DecideRequest.model_validate(payload)
    from app.decision.engine import DecisionEngine
    pre = DecisionEngine().evaluate(order, StrategySnapshot()).response.economics.adjusted_rate_mxn_hr
    snapshot = StrategySnapshot(reservation_wage_mxn_hr=pre + 10)
    config = GeminiConfig(enabled=True, api_key='fake')
    advisor = GeminiStrategyAdvisor(FakeClient(), config)
    agent = SmartAgentWithGemini(snapshot, advisor)
    asyncio.run(advisor.prewarm(order, snapshot))
    response = agent.decide_request(order)
    assert response.decision == 'ACCEPT' and response.llm_changed_decision
    metrics = agent.service.gemini_metrics()
    assert metrics['llm_changed_decisions'] == metrics['llm_changed_to_accept'] == 1
    assert metrics['gemini_calls'] == 1 and metrics['gemini_cache_hits'] >= 1
    assert metrics['net_gain_from_llm_changed_decisions'] is None

def test_invalid_advice_falls_back(payload):
    agent, advisor, _, order = setup(payload, FakeClient({'recommendation': 'ACCEPT'}))
    assert asyncio.run(advisor.prewarm(order, agent.snapshot)) is None
    response = agent.decide_request(order)
    assert response.degraded and response.llm_adjustment_mxn_hr == 0
    assert advisor.failures == 1

def test_prewarm_endpoint_and_explanation_grounding(payload):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.llm.explanation_service import GeminiExplanationService
    agent, advisor, fake, order = setup(payload)
    with TestClient(create_app(advisor=advisor)) as client:
        warmed = client.post('/strategy/advisory/prewarm', json=payload)
        assert warmed.status_code == 200 and warmed.json()['available']
        decision = client.post('/decide', json=payload)
        assert decision.status_code == 200 and decision.json()['gemini_cache_hit']
    class Hallucinating:
        async def explain(self, facts): return 'A better order will arrive in 10 minutes.'
    record = agent.decide_request(order)
    log = agent.service.log.get(order.order_id)
    assert asyncio.run(GeminiExplanationService(Hallucinating()).explain(log)) is None
