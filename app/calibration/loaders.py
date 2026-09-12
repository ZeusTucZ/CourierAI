"""Explicit column mapping. Missing measurements stay None; units are caller-owned."""
import csv
import json
from datetime import datetime
from pathlib import Path

from pydantic import Field

from app.models.common import Model, NonNegative


class NormalizedDeliveryRecord(Model):
    timestamp: datetime | None = None
    pickup_zone: int | None = Field(default=None, ge=1)
    dropoff_zone: int | None = Field(default=None, ge=1)
    distance_km: NonNegative | None = None
    pickup_distance_km: NonNegative | None = None
    prep_time_min: NonNegative | None = None
    service_time_min: NonNegative | None = None
    base_pay_mxn: NonNegative | None = None
    tip_mxn: NonNegative | None = None
    demand_weight: NonNegative | None = None
    demand_volume: NonNegative | None = None


def load_records(path: Path, columns: dict[str, str] | None = None) -> tuple[NormalizedDeliveryRecord, ...]:
    """CSV, JSON array, or JSONL. Mapping is internal field -> external column."""
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    elif path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Expected an array of records")
    mapping = columns or {key: key for key in NormalizedDeliveryRecord.model_fields}
    if set(mapping) - NormalizedDeliveryRecord.model_fields.keys():
        raise ValueError("Unknown normalized field in column mapping")
    result = []
    for index, row in enumerate(rows, 1):
        data = {key: row.get(column) for key, column in mapping.items() if row.get(column) not in (None, "")}
        try:
            if path.suffix.lower() == ".csv":
                data = {key: (value if key == "timestamp" else int(value) if key in {"pickup_zone", "dropoff_zone"} else float(value))
                        for key, value in data.items()}
            result.append(NormalizedDeliveryRecord.model_validate(data))
        except ValueError as exc:
            raise ValueError(f"Invalid data at record {index}: {exc}") from exc
    return tuple(result)


def load_solomon(path: Path, *, demand_to_kg: float | None = None,
                 service_to_minutes: float | None = None) -> tuple[NormalizedDeliveryRecord, ...]:
    """Solomon CUSTOMER rows: id x y demand ready due service.

    Coordinate distance is NOT road km; ready/due are NOT timestamps. Only
    explicitly supplied unit conversions populate weight/service measurements.
    """
    if any(value is not None and value <= 0 for value in (demand_to_kg, service_to_minutes)):
        raise ValueError("Unit conversions must be positive")
    text = path.read_text(encoding="utf-8")
    if "CUSTOMER" not in text.upper():
        raise ValueError("Missing Solomon CUSTOMER section")
    lines = text.upper().split("CUSTOMER", 1)[1].splitlines()
    records = []
    for line in lines:
        parts = line.split()
        if len(parts) != 7:
            continue
        try:
            ident, x, y, demand, ready, due, service = map(float, parts)
        except ValueError:
            continue
        if ident == 0:  # Depot is not a customer delivery.
            continue
        records.append(NormalizedDeliveryRecord(
            demand_weight=None if demand_to_kg is None else demand * demand_to_kg,
            service_time_min=None if service_to_minutes is None else service * service_to_minutes))
    if not records:
        raise ValueError("No customer rows found")
    return tuple(records)
