import asyncio
import os
from dataclasses import dataclass
from app.llm.schemas import StrategyAdvice
from app.llm.prompts import STRATEGY_SYSTEM_PROMPT, EXPLANATION_SYSTEM_PROMPT

@dataclass(frozen=True)
class GeminiConfig:
    enabled: bool = False
    api_key: str | None = None
    model: str = 'gemini-3.6-flash'
    timeout_ms: int = 10000
    max_retries: int = 0
    ttl_sim_min: float = 10
    min_adjustment: float = -20
    max_adjustment: float = 20

    def __post_init__(self):
        if self.timeout_ms <= 0 or self.max_retries < 0 or self.ttl_sim_min <= 0:
            raise ValueError('Gemini timeout, retries or TTL out of range')
        if self.min_adjustment > 0 or self.max_adjustment < 0 or self.min_adjustment > self.max_adjustment:
            raise ValueError('Adjustment bounds must contain zero')

    @classmethod
    def from_env(cls):
        return cls(enabled=os.getenv('GEMINI_ENABLED', 'false').lower() == 'true',
            api_key=os.getenv('GEMINI_API_KEY'), model=os.getenv('GEMINI_MODEL', 'gemini-3.6-flash'),
            timeout_ms=int(os.getenv('GEMINI_TIMEOUT_MS', '10000')),
            max_retries=int(os.getenv('GEMINI_MAX_RETRIES', '0')),
            ttl_sim_min=float(os.getenv('GEMINI_ADVISORY_TTL_SIM_MIN', '10')),
            min_adjustment=float(os.getenv('LLM_MIN_ADJUSTMENT_MXN_HR', '-20')),
            max_adjustment=float(os.getenv('LLM_MAX_ADJUSTMENT_MXN_HR', '20')))

class GeminiClient:
    def __init__(self, config: GeminiConfig):
        self.config = config
        self.client = None
        if config.enabled and config.api_key:
            from google import genai
            from google.genai import types
            self.client = genai.Client(api_key=config.api_key, http_options=types.HttpOptions(timeout=config.timeout_ms))

    async def analyze(self, payload: str) -> StrategyAdvice:
        if self.client is None:
            raise RuntimeError('Gemini disabled or API key missing')
        from google.genai import types
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await asyncio.wait_for(self.client.aio.models.generate_content(
                    model=self.config.model, contents=payload,
                    config=types.GenerateContentConfig(system_instruction=STRATEGY_SYSTEM_PROMPT,
                        response_mime_type='application/json',
                        response_json_schema=StrategyAdvice.model_json_schema())),
                    timeout=self.config.timeout_ms / 1000)
                return StrategyAdvice.model_validate_json(response.text)
            except Exception:
                if attempt == self.config.max_retries:
                    raise

    async def explain(self, payload: str) -> str:
        if self.client is None:
            raise RuntimeError('Gemini disabled or API key missing')
        from google.genai import types
        response = await asyncio.wait_for(self.client.aio.models.generate_content(
            model=self.config.model, contents=payload,
            config=types.GenerateContentConfig(system_instruction=EXPLANATION_SYSTEM_PROMPT)),
            timeout=self.config.timeout_ms / 1000)
        return (response.text or '').strip()
