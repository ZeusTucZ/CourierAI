"""Build explicitly SYNTHETIC historical calibration from authorized tuning seeds."""
import json
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

from app.calibration.fitting import calibrate
from app.calibration.loaders import NormalizedDeliveryRecord
from app.evaluation.runner import seed_sets
from app.simulation.config import ShiftConfig, SyntheticConfig
from app.simulation.generator import generate_shift
from app.strategy.historical import HistoricalDemandModel


def main():
    seeds, _ = seed_sets()
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    records = []
    for index, seed in enumerate(seeds):
        settings = SyntheticConfig(simulation_start_time=datetime(2026, 2, 1, 15) + timedelta(days=index), shock_schedule=())
        cfg = ShiftConfig(seed=seed, shift_hours=8, vehicle="moto", start_location_zone=7, simulation=settings)
        for event in generate_shift(cfg):
            if event["event"] != "order_offered":
                continue
            records.append(NormalizedDeliveryRecord(timestamp=event["sim_time"], pickup_zone=event["zone_pickup"], dropoff_zone=event["zone_dropoff"],
                distance_km=event["distance_delivery_km"], pickup_distance_km=event["distance_pickup_km"],
                prep_time_min=event["restaurant_prep_min"], service_time_min=(event["distance_delivery_km"] + event["distance_pickup_km"]) / 25 * 60 + event["restaurant_prep_min"],
                base_pay_mxn=event["base_pay_mxn"], tip_mxn=event["est_tip_mxn"], demand_weight=event["weight_kg"], demand_volume=event["volume_liters"]))
    path = output / "synthetic_tuning_history.json"
    path.write_text(json.dumps([row.model_dump(mode="json") for row in records], indent=2) + "\n")
    digest = sha256(path.read_bytes()).hexdigest()
    profile, report = calibrate(records, source=str(path), source_sha256=digest, exposure_hours=8 * len(seeds), training_seeds=seeds, synthetic=True,
                                hour_exposure={h: len(seeds) for h in range(15, 23)})
    profile.save(output / "calibrated_profile.json")
    model = HistoricalDemandModel.fit(records, hour_exposure={h: len(seeds) for h in range(15, 23)},
        training_seeds=seeds, source="Synthetic MVP 2 tuning history; no real observations", source_sha256=digest)
    (output / "historical_model.json").write_text(model.model_dump_json(indent=2) + "\n")
    (output / "calibration_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "calibration_manifest.json").write_text(json.dumps({"classification": "synthetic",
        "source": str(path), "source_sha256": digest, "training_seeds": seeds,
        "parameters": [p.model_dump() for p in profile.provenance], "profile": profile.model_dump(mode="json"),
        "service_formula": "(pickup_km + delivery_km) / assumed 25 km/h * 60 + prep_min",
        "observation_exposure_hours": 8 * len(seeds), "historical_hour_exposure": {h: len(seeds) for h in range(15, 23)}}, indent=2) + "\n")
    print(f"Prepared {len(records)} SYNTHETIC records from tuning seeds {seeds}; no heldout data used.")


if __name__ == "__main__":
    main()
