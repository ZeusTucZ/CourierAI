from app.llm.schemas import StrategyAdvice

NEUTRAL_ADVICE = StrategyAdvice(recommendation='NEUTRAL', confidence=0,
    demand_outlook='MEDIUM', destination_quality='NEUTRAL', opportunity_risk='MEDIUM',
    key_factors=[], explanation='No valid Gemini advisory is available.')

def adjustment(advice: StrategyAdvice, minimum: float = -20, maximum: float = 20) -> float:
    if minimum > 0 or maximum < 0 or minimum > maximum:
        raise ValueError('Adjustment bounds must contain zero')
    if advice.recommendation == 'NEUTRAL':
        return 0.0
    demand = {'LOW': -1, 'MEDIUM': 0, 'HIGH': 1}[advice.demand_outlook]
    destination = {'POOR': -1, 'NEUTRAL': 0, 'GOOD': 1}[advice.destination_quality]
    risk = {'LOW': 1, 'MEDIUM': 0, 'HIGH': -1}[advice.opportunity_risk]
    direction = 1 if advice.recommendation == 'ACCEPT' else -1
    raw = advice.confidence * (5 * direction + 5 * demand + 5 * destination + 5 * risk)
    return max(minimum, min(maximum, raw))
