import json
import re


def _display_facts(value):
    """Round prompt-only numbers; never mutate recorded decision facts."""
    if isinstance(value, dict):
        return {key: _display_facts(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_display_facts(item) for item in value]
    if isinstance(value, float):
        return f'{value:.2f}'
    if isinstance(value, str):
        return re.sub(r'(?<![\w.])\d+\.\d+(?![\w.])',
                      lambda match: f'{float(match.group()):.2f}', value)
    return value


class GeminiExplanationService:
    def __init__(self, client):
        self.client = client

    async def explain(self, record, advice=None):
        facts = {'decision': record.decision, 'structured_reason': record.reason,
                 'economics': record.economics.model_dump(mode='json') if record.economics else None,
                 'advice': advice.model_dump(mode='json') if advice else None}
        return await self.explain_facts(facts)

    async def explain_facts(self, facts: dict) -> str | None:
        try:
            display_facts = _display_facts(facts)
            candidate = await self.client.explain(json.dumps(display_facts, sort_keys=True, ensure_ascii=False))
            # A conservative grounding gate: reject unsupported numbers and future claims.
            allowed = set(re.findall(r'\d+(?:\.\d+)?', json.dumps(display_facts)))
            numbers = set(re.findall(r'\d+(?:\.\d+)?', candidate))
            spanish = r'(?i)\b(el pedido|se rechaz[oó]|se acept[oó]|porque|repartidor|tarifa|turno|minutos)\b'
            if numbers - allowed or re.search(r'(?i)\b(will arrive|next order|future shock)\b', candidate) or re.search(spanish, candidate):
                return None
            return candidate[:500] or None
        except Exception:
            return None


def fallback_explanation(decision: dict) -> str:
    """Grounded, readable text when Gemini is unavailable or its answer is rejected."""
    reason = decision.get('reason', '')
    constraint = decision.get('binding_constraint')
    if constraint == 'shift_end_infeasible':
        match = re.search(r'([\d.]+) minutes after shift end', reason)
        if match:
            return (f"This order was skipped because completing it would exceed the shift end by "
                    f"{float(match.group(1)):.2f} minutes, including work already in progress.")
        return 'This order was skipped because there is not enough time left in the shift to complete it.'
    explanations = {
        'vehicle_capacity': 'This order exceeds the vehicle capacity or the available load information cannot verify it safely.',
        'mandatory_break': 'The courier must take the required break before accepting more work.',
        'heat_rule': 'The heat safety rule prevents this trip at the current riding duration.',
        'flagged_zone_night': 'This drop-off falls in a restricted zone during nighttime hours.',
    }
    if constraint in explanations:
        return explanations[constraint]
    if constraint == 'reservation_wage':
        economics = decision.get('economics') or {}
        rate, wage, duration = (economics.get(key) for key in
            ('adjusted_rate_mxn_hr', 'reservation_wage_mxn_hr', 'total_time_min'))
        if all(isinstance(value, (float, int)) for value in (rate, wage, duration)):
            if round(rate, 2) == round(wage, 2):
                return 'This order narrowly misses Smart’s minimum hourly rate before rounding.'
            return (f'This order was skipped because its adjusted rate of MXN {rate:.2f}/hour '
                    f'is below the required MXN {wage:.2f}/hour over {duration:.2f} minutes.')
        return 'The estimated value of this order does not meet Smart’s minimum hourly rate.'
    if decision.get('decision') == 'ACCEPT':
        return 'Smart accepted this order because it meets the safety checks and its minimum economic threshold.'
    return 'Smart skipped this order because it does not meet the recorded acceptance conditions.'
