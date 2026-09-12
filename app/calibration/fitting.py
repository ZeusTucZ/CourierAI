from collections import Counter
from statistics import mean, median
from math import ceil

from app.calibration.loaders import NormalizedDeliveryRecord
from app.calibration.profiles import CalibratedProfile, Distribution, Provenance, SyntheticProfile, Transition


FIELDS = {
    "pickup_distance_distribution": "pickup_distance_km", "order_distance_distribution": "distance_km",
    "prep_time_distribution": "prep_time_min", "service_time_distribution": "service_time_min",
    "base_pay_distribution": "base_pay_mxn", "tip_distribution": "tip_mxn",
    "weight_distribution": "demand_weight", "volume_distribution": "demand_volume",
}


def calibrate(records, *, source, source_sha256=None, exposure_hours=None,
              training_seeds=(), synthetic=False, hour_exposure=None):
    if not records:
        raise ValueError("Cannot calibrate an empty dataset")
    base = SyntheticProfile()
    changes, manifest = {}, []
    classification = "synthetic" if synthetic else "observed"
    for parameter, field in FIELDS.items():
        values = tuple(getattr(row, field) for row in records if getattr(row, field) is not None)
        if values:
            changes[parameter] = Distribution(kind="empirical", values=values)
        manifest.append(Provenance(parameter=parameter, source=source if values else "SyntheticProfile defaults",
            classification=classification if values else "assumed", sample_size=len(values),
            transformation="Empirical bootstrap of non-missing measurements; supplied normalized units",
            fallback=None if values else str(getattr(base, parameter))))
    stamps = [row.timestamp for row in records if row.timestamp is not None]
    # Exposure is supplied explicitly, never inferred from sparse event endpoints.
    if exposure_hours is not None:
        if exposure_hours <= 0:
            raise ValueError("exposure_hours must be positive")
        changes["orders_per_hour"] = len(records) / exposure_hours
    manifest.append(Provenance(parameter="orders_per_hour", source=source if exposure_hours else "SyntheticProfile defaults",
        classification=("synthetic" if synthetic else "derived") if exposure_hours else "assumed",
        sample_size=len(records), transformation="record count / explicitly declared total observation hours",
        fallback=None if exposure_hours else "15 orders/hour; observation exposure unknown"))
    transitions = Counter((r.pickup_zone, r.dropoff_zone) for r in records if r.pickup_zone is not None and r.dropoff_zone is not None)
    changes["zone_transition_distribution"] = tuple(Transition(pickup=a, dropoff=b, count=n) for (a, b), n in sorted(transitions.items()))
    manifest.append(Provenance(parameter="zone_transition_distribution", source=source,
        classification=classification, sample_size=sum(transitions.values()), transformation="Count paired pickup/dropoff zones",
        fallback=None if transitions else "Uniform synthetic zones"))
    # Timestamp frequency alone cannot identify hourly demand without bucket exposure.
    if hour_exposure is not None:
        if any(not 0 <= int(h) <= 23 or hours <= 0 for h, hours in hour_exposure.items()):
            raise ValueError("Hourly exposure must have valid hours and positive durations")
        counts = Counter(t.hour for t in stamps)
        rate = changes.get("orders_per_hour", base.orders_per_hour)
        changes["time_of_day_demand_profile"] = tuple(counts[h] / hour_exposure[h] / rate if h in hour_exposure else 1 for h in range(24))
    manifest.append(Provenance(parameter="time_of_day_demand_profile", source=source if hour_exposure else "configured",
        classification=("synthetic" if synthetic else "derived") if hour_exposure else "assumed",
        sample_size=len(stamps) if hour_exposure else 0, transformation="hourly count / hourly exposure / overall rate" if hour_exposure else "Flat demand; hourly exposure not supplied",
        fallback="Unobserved hours use factor 1; zero observed demand uses factor 0" if hour_exposure else "24 factors equal to 1; report frequencies separately"))
    profile = CalibratedProfile(name="calibrated-" + (source_sha256 or "local")[:12],
        provenance=tuple(manifest), training_seeds=tuple(training_seeds), source_sha256=source_sha256, **changes)
    missingness = {field: sum(getattr(row, field) is None for row in records) / len(records)
                   for field in NormalizedDeliveryRecord.model_fields}
    statistics = {}
    for field in FIELDS.values():
        values = sorted(getattr(row, field) for row in records if getattr(row, field) is not None)
        statistics[field] = {"n": len(values), "mean": mean(values), "median": median(values),
                             "p95": values[ceil(.95 * len(values)) - 1]} if values else None
    report = {"n_records": len(records), "orders_per_hour": len(records) / exposure_hours if exposure_hours else None,
        "exposure_hours": exposure_hours, "statistics": statistics, "missingness": missingness,
        "zone_frequencies": dict(sorted(Counter(r.pickup_zone for r in records if r.pickup_zone is not None).items())),
        "hour_of_day_frequencies": dict(sorted(Counter(t.hour for t in stamps).items()))}
    return profile, report
