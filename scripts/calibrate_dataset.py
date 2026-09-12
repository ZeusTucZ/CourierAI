import argparse
import json
from hashlib import sha256
from pathlib import Path

from app.calibration.loaders import load_records, load_solomon
from app.calibration.fitting import calibrate
from app.strategy.historical import HistoricalDemandModel


def main():
    parser = argparse.ArgumentParser(description="Offline calibration with explicit provenance")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--columns", type=Path, help="JSON internal-field -> source-column mapping")
    parser.add_argument("--adapter", choices=("table", "solomon"), default="table")
    parser.add_argument("--demand-to-kg", type=float)
    parser.add_argument("--service-to-minutes", type=float)
    parser.add_argument("--exposure-hours", type=float)
    parser.add_argument("--hour-exposure", type=Path, help="JSON hour -> observed hours; also builds historical_model.json")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    hourly = {int(h): v for h, v in json.loads(args.hour_exposure.read_text()).items()} if args.hour_exposure else None
    records = load_solomon(args.dataset, demand_to_kg=args.demand_to_kg, service_to_minutes=args.service_to_minutes) if args.adapter == "solomon" else load_records(args.dataset, json.loads(args.columns.read_text()) if args.columns else None)
    profile, report = calibrate(records, source=str(args.dataset), source_sha256=sha256(args.dataset.read_bytes()).hexdigest(),
                                exposure_hours=args.exposure_hours, synthetic=args.synthetic, hour_exposure=hourly)
    profile.save(args.output_dir / "calibrated_profile.json")
    manifest = {"profile": profile.model_dump(mode="json"), "parameters": [p.model_dump() for p in profile.provenance],
                "adapter": args.adapter, "column_mapping": str(args.columns),
                "demand_to_kg": args.demand_to_kg, "service_to_minutes": args.service_to_minutes}
    (args.output_dir / "calibration_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (args.output_dir / "calibration_report.json").write_text(json.dumps(report, indent=2) + "\n")
    if hourly:
        model = HistoricalDemandModel.fit(records, hour_exposure=hourly, source=str(args.dataset),
                                           source_sha256=profile.source_sha256)
        (args.output_dir / "historical_model.json").write_text(model.model_dump_json(indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
