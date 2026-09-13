import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from time import perf_counter
from app.decision.economics import calculate_economics
from app.decision.timing import build_work_plan
from app.models.state import resolve_state
from app.llm.fallback import adjustment


def observable_context(order, snapshot, *, environment=None):
    state = resolve_state(order.sim_time, order.courier_state_overrides, snapshot.policy.default_shift_hours)
    plan = build_work_plan(order, state, snapshot)
    economics = calculate_economics(order, snapshot, plan)
    current = snapshot.zone_predictions.get(order.zone_pickup)
    destination = snapshot.zone_predictions.get(order.zone_dropoff)
    return {
        'sim_time': order.sim_time.isoformat(), 'vehicle': order.vehicle,
        'current_zone': order.zone_pickup,
        'time_remaining_min': (state.shift_end_time - order.sim_time).total_seconds() / 60,
        'current_order': {'base_pay_mxn': order.base_pay_mxn, 'surge_multiplier': order.surge_multiplier,
            'tip_mxn': order.est_tip_mxn, 'pickup_distance_km': order.distance_pickup_km,
            'delivery_distance_km': order.distance_delivery_km, 'estimated_total_time_min': plan.total_time_min,
            'dropoff_zone': order.zone_dropoff},
        'current_state': {'active_orders': len(state.in_flight_orders),
            'current_load_kg': sum(x.weight_kg for x in state.in_flight_orders) if all(x.weight_kg is not None for x in state.in_flight_orders) else None,
            'continuous_riding_min': state.continuous_riding_min},
        'economics': {'net_pay_mxn': economics.net_pay_mxn, 'raw_rate_mxn_hr': economics.raw_rate_mxn_hr,
            'reservation_wage_mxn_hr': economics.reservation_wage_mxn_hr,
            'opportunity_cost_mxn': economics.opportunity_cost_mxn,
            'dropoff_zone_value': snapshot.zone_values.get(order.zone_dropoff)},
        'historical_context': {'current_zone_expected_orders_per_hour': current.expected_orders_per_hour if current else None,
            'dropoff_zone_expected_orders_per_hour': destination.expected_orders_per_hour if destination else None,
            'expected_trip_distance_km': current.expected_trip_distance if current else None,
            'sample_count': current.sample_count if current else None},
        'environment': environment,
    }

@dataclass(frozen=True)
class CachedAdvice:
    advice: object
    generated_at: datetime
    latency_ms: float

class GeminiStrategyAdvisor:
    def __init__(self, client, config):
        self.client, self.config = client, config
        self.cache = {}
        self.calls = self.failures = self.timeouts = self.cache_hits = 0
        self.latencies = []
        self.last_error = None

    def key(self, context, profile_version):
        stable = {key: value for key, value in context.items() if key not in ('sim_time', 'time_remaining_min')}
        hour = datetime.fromisoformat(context['sim_time']).hour
        return sha256(json.dumps([stable, hour, profile_version], sort_keys=True, default=str).encode()).hexdigest()

    def get(self, context, profile_version):
        entry = self.cache.get(self.key(context, profile_version))
        if entry and timedelta(0) <= datetime.fromisoformat(context['sim_time']) - entry.generated_at < timedelta(minutes=self.config.ttl_sim_min):
            self.cache_hits += 1
            return entry
        return None

    async def analyze(self, context, profile_version):
        cached = self.get(context, profile_version)
        if cached:
            return cached.advice
        if not self.config.enabled or not self.config.api_key:
            self.last_error = 'Gemini disabled or API key missing'
            return None

        start = perf_counter()
        self.calls += 1
        try:
            from app.llm.schemas import StrategyAdvice
            advice = StrategyAdvice.model_validate(await self.client.analyze(json.dumps(context, sort_keys=True)))
            elapsed = (perf_counter() - start) * 1000
            self.latencies.append(elapsed)
            self.cache[self.key(context, profile_version)] = CachedAdvice(advice, datetime.fromisoformat(context['sim_time']), elapsed)
            self.last_error = None
            return advice
        except Exception as exc:
            self.failures += 1
            if isinstance(exc, TimeoutError):
                self.timeouts += 1
            self.last_error = type(exc).__name__
            return None

    async def prewarm(self, order, snapshot, *, environment=None):
        return await self.analyze(observable_context(order, snapshot, environment=environment), snapshot.version)

    def metrics(self):
        return {'gemini_calls': self.calls, 'gemini_failures': self.failures,
            'gemini_timeouts': self.timeouts, 'gemini_cache_hits': self.cache_hits,
            'gemini_mean_latency_ms': sum(self.latencies) / len(self.latencies) if self.latencies else None}
