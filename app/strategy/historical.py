"""Offline zone/hour aggregates. No access to generator, RNG or live streams."""
from collections import defaultdict
from datetime import datetime
from statistics import mean

from pydantic import Field

from app.models.common import Model, NonNegative
from app.config.vehicles import default_vehicle_profiles
from app.strategy.models import ZonePrediction


class DemandBucket(Model):
    zone: int
    hour: int = Field(ge=0, le=23)
    orders_per_hour: NonNegative
    gross_pay: NonNegative
    distance_km: NonNegative
    service_min: NonNegative
    sample_count: int = Field(ge=0)


class HistoricalDemandModel(Model):
    buckets: tuple[DemandBucket, ...] = ()
    training_seeds: tuple[int, ...] = ()
    source: str = "unspecified"
    source_sha256: str | None = None
    trained_through: datetime | None = None
    min_samples: int = Field(default=5, ge=1)

    @classmethod
    def fit(cls, records, *, hour_exposure: dict[int, float], training_seeds=(), source="local", source_sha256=None):
        groups = defaultdict(list)
        stamps = [r.timestamp for r in records if r.timestamp is not None]
        for row in records:
            if row.timestamp is not None and row.pickup_zone is not None:
                groups[(row.pickup_zone, row.timestamp.hour)].append(row)
        buckets = []
        for (zone, hour), rows in sorted(groups.items()):
            exposure = hour_exposure.get(hour, 0)
            if exposure <= 0:
                raise ValueError(f"Missing positive observation exposure for hour {hour}")
            complete = [r for r in rows if all(getattr(r, name) is not None for name in
                        ("base_pay_mxn", "tip_mxn", "distance_km", "pickup_distance_km", "service_time_min"))]
            # Unknown economics is excluded, not silently treated as zero pay/cost.
            if not complete:
                continue
            buckets.append(DemandBucket(zone=zone, hour=hour, orders_per_hour=len(rows) / exposure,
                gross_pay=mean(r.base_pay_mxn + r.tip_mxn for r in complete),
                distance_km=mean(r.distance_km + r.pickup_distance_km for r in complete),
                service_min=mean(r.service_time_min for r in complete), sample_count=len(complete)))
        return cls(buckets=tuple(buckets), training_seeds=tuple(training_seeds), source=source,
                   source_sha256=source_sha256, trained_through=max(stamps) if stamps else None)

    def predict_zone_value(self, zone: int, sim_time: datetime, vehicle: str) -> ZonePrediction:
        if self.trained_through is not None and sim_time <= self.trained_through:
            raise ValueError("Prediction time must follow historical training cutoff")
        exact = next((b for b in self.buckets if b.zone == zone and b.hour == sim_time.hour), None)
        pool = [b for b in self.buckets if b.hour == sim_time.hour] or list(self.buckets)
        use_exact = exact is not None and exact.sample_count >= self.min_samples
        selected = [exact] if use_exact else pool
        if not selected:
            return ZonePrediction(zone=zone, time_bucket=sim_time.hour, fallback=True)
        rate = mean(b.orders_per_hour for b in selected)
        gross = mean(b.gross_pay for b in selected)
        cost = mean(b.distance_km for b in selected) * default_vehicle_profiles()[vehicle].operating_cost_mxn_per_km
        service = mean(b.service_min for b in selected)
        wait = 60 / rate if rate else None
        hourly = max(0, gross - cost) * 60 / (service + wait) if wait is not None else 0
        count = exact.sample_count if exact else 0
        return ZonePrediction(zone=zone, time_bucket=sim_time.hour, expected_orders_per_hour=rate,
            expected_gross_pay=gross, expected_net_pay=gross - cost, expected_wait_time_min=wait,
            expected_net_mxn_per_hour=hourly, sample_count=count,
            confidence=min(1, count / self.min_samples), fallback=not use_exact)
