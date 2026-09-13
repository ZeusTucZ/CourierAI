import json
import re

class GeminiExplanationService:
    def __init__(self, client):
        self.client = client

    async def explain(self, record, advice=None):
        facts = {'decision': record.decision, 'structured_reason': record.reason,
                 'economics': record.economics.model_dump(mode='json') if record.economics else None,
                 'advice': advice.model_dump(mode='json') if advice else None}
        try:
            candidate = await self.client.explain(json.dumps(facts, sort_keys=True))
            # A conservative grounding gate: reject unsupported numbers and future claims.
            allowed = set(re.findall(r'\d+(?:\.\d+)?', json.dumps(facts)))
            numbers = set(re.findall(r'\d+(?:\.\d+)?', candidate))
            if numbers - allowed or re.search(r'(?i)\b(will arrive|next order|future shock|llegar[aá]|pr[oó]ximo pedido)\b', candidate):
                return None
            return candidate[:500] or None
        except Exception:
            return None
