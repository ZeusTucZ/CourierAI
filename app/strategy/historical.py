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
    orders_per_hour: NonNegative | None
    gross_pay: NonNegative | None
    distance_km: NonNegative | None
    service_min: NonNegative | None
    sample_count: int = Field(ge=0)


class HistoricalDemandModel(Model):
    buckets: tuple[DemandBucket, ...] = ()
    training_seeds: tuple[int, ...] = ()
    source: str = "unspecified"
    source_sha256: str | None = None
    trained_through: datetime | None = None
    min_samples: int = Field(default=5, ge=1)

    @classmethod
    def fit(cls, records, *, hour_exposure: dict[int, float] | None, training_seeds=(), source="local", source_sha256=None, training_cutoff=None):
        if training_cutoff is not None:
            records = tuple(r for r in records if r.timestamp is not None and r.timestamp <= training_cutoff)
        groups = defaultdict(list)
        stamps = [r.timestamp for r in records if r.timestamp is not None]
        for row in records:
            if row.timestamp is not None and row.pickup_zone is not None:
                groups[(row.pickup_zone, row.timestamp.hour)].append(row)
        buckets = []
        for (zone, hour), rows in sorted(groups.items()):
            exposure = hour_exposure.get(hour, 0) if hour_exposure is not None else None
            if exposure is not None and exposure <= 0:
                raise ValueError(f"Missing positive observation exposure for hour {hour}")
            complete = [r for r in rows if all(getattr(r, name) is not None for name in
                        ("base_pay_mxn", "tip_mxn", "distance_km", "pickup_distance_km", "service_time_min"))]
            def measured(field):
                values = [getattr(r, field) for r in rows if getattr(r, field) is not None]
                return mean(values) if values else None
            buckets.append(DemandBucket(zone=zone, hour=hour,
                orders_per_hour=len(rows) / exposure if exposure else None,
                gross_pay=mean(r.base_pay_mxn + r.tip_mxn for r in complete) if complete else None,
                distance_km=mean(r.distance_km + r.pickup_distance_km for r in complete) if complete else measured("distance_km"),
                service_min=measured("service_time_min"), sample_count=len(rows)))
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
            return ZonePrediction(zone=zone, time_bucket=sim_time.hour, fallback=True, economics_available=False,
                                  expected_orders_per_hour=None, expected_gross_pay=None, expected_net_pay=None, expected_net_mxn_per_hour=None)
        def aggregate(field):
            available = [b for b in selected if getattr(b, field) is not None]
            return (sum(getattr(b, field) * b.sample_count for b in available) /
                    sum(b.sample_count for b in available)) if available else None
        rate, gross = aggregate("orders_per_hour"), aggregate("gross_pay")
        distance, service = aggregate("distance_km"), aggregate("service_min")
        count = exact.sample_count if exact else 0
        common = dict(zone=zone, time_bucket=sim_time.hour, expected_orders_per_hour=rate,
            expected_trip_distance=distance, expected_delivery_time=service,
            sample_count=count, confidence=min(1, count / self.min_samples), fallback=not use_exact)
        if gross is None or distance is None or service is None or rate is None:
            return ZonePrediction(**common, economics_available=False,
                                  expected_gross_pay=None, expected_net_pay=None, expected_net_mxn_per_hour=None)
        cost = distance * default_vehicle_profiles()[vehicle].operating_cost_mxn_per_km
        wait = 60 / rate if rate else None
        hourly = max(0, gross - cost) * 60 / (service + wait) if wait is not None else 0
        return ZonePrediction(**common, expected_gross_pay=gross, expected_net_pay=gross - cost,
            expected_wait_time_min=wait, expected_net_mxn_per_hour=hourly)
