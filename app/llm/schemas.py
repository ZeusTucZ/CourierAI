from typing import Literal
from pydantic import Field
from app.models.common import Model

class StrategyAdvice(Model):
    recommendation: Literal['ACCEPT', 'SKIP', 'NEUTRAL']
    confidence: float = Field(ge=0, le=1)
    demand_outlook: Literal['LOW', 'MEDIUM', 'HIGH']
    destination_quality: Literal['POOR', 'NEUTRAL', 'GOOD']
    opportunity_risk: Literal['LOW', 'MEDIUM', 'HIGH']
    key_factors: list[str]
    explanation: str
