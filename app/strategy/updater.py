from statistics import mean

from app.models.strategy import StrategySnapshot
from app.strategy.models import StrategyPolicy


class StrategyUpdater:
    def __init__(self, model, policy: StrategyPolicy, zones):
        self.model, self.policy, self.zones = model, policy, tuple(sorted(zones))

    def update(self, store, sim_time, vehicle, remaining_min, *, available=True):
        previous = store.get()
        try:
            if not available:
                raise ConnectionError("Simulated prediction service unavailable")
            predictions = {zone: self.model.predict_zone_value(zone, sim_time, vehicle) for zone in self.zones} if self.policy.use_historical_prediction else {}
            reference = mean((p.expected_net_mxn_per_hour or 0) for p in predictions.values()) if predictions else 0
            clip = self.policy.zone_value_clip
            values = {z: max(-clip, min(clip, (p.expected_net_mxn_per_hour or 0) - reference)) for z, p in predictions.items()} if self.policy.use_zone_value else {}
            wage = self.policy.base_reservation_wage + reference * self.policy.demand_adjustment_fraction - self.policy.final_hour_discount * max(0, 1 - remaining_min / 60)
            wage = max(self.policy.min_reservation_wage, min(self.policy.max_reservation_wage, wage))
            target = min(predictions, key=lambda z: (-(predictions[z].expected_net_mxn_per_hour or 0), z)) if predictions else None
            data = {**previous.model_dump(mode="json"), "version": "mvp3:" + sim_time.isoformat(),
                "strategy_version": "historical-v1", "generated_at_sim_time": sim_time,
                "zone_predictions": predictions, "zone_values": values, "target_zone": target,
                "reservation_wage_mxn_hr": wage, "is_stale": False,
                "economics_v2": True, "opportunity_fraction": self.policy.opportunity_fraction,
                "skip_penalty_mxn": self.policy.skip_penalty_mxn}
            snapshot = StrategySnapshot.model_validate(data)
        except (ConnectionError, TimeoutError):
            snapshot = StrategySnapshot.model_validate({**previous.model_dump(mode="json"), "is_stale": True})
        store.replace(snapshot)
        return snapshot
