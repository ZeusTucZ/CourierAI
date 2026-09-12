"""Capture seven live demo decisions; not a simulator or earnings evaluation."""
import argparse
import json
import urllib.request
from pathlib import Path


def demo_offers():
    base = {
        "order_id": "DEMO-ACCEPT", "platform": "rappi", "sim_time": "2026-03-21T18:00:00",
        "zone_pickup": 7, "zone_dropoff": 7, "distance_pickup_km": 1,
        "distance_delivery_km": 2, "base_pay_mxn": 100, "est_tip_mxn": 10,
        "surge_multiplier": 1, "restaurant_prep_min": 0, "weight_kg": 1,
        "volume_liters": 2, "vehicle": "moto", "estimated_pickup_min": 5,
        "estimated_delivery_min": 5,
        "courier_state_overrides": {"continuous_riding_min": 0, "shift_end_time": "2026-03-21T23:00:00"},
    }
    return [base,
        {**base, "order_id": "DEMO-PAY", "base_pay_mxn": 0, "est_tip_mxn": 0},
        {**base, "order_id": "DEMO-NIGHT", "sim_time": "2026-03-21T22:00:00", "zone_dropoff": 11},
        {**base, "order_id": "DEMO-BREAK", "courier_state_overrides": {"continuous_riding_min": 240}},
        {**base, "order_id": "DEMO-HEAT", "sim_time": "2026-03-21T12:00:00",
         "courier_state_overrides": {"continuous_riding_min": 90}},
        {**base, "order_id": "DEMO-SHIFT", "courier_state_overrides": {"shift_end_time": "2026-03-21T18:05:00"}},
        {**base, "order_id": "DEMO-CAPACITY", "weight_kg": 16},
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://localhost:8000/decide")
    parser.add_argument("--output", type=Path, default=Path("examples/responses.json"))
    args = parser.parse_args()
    responses = []
    for offer in demo_offers():
        request = urllib.request.Request(args.endpoint, data=json.dumps(offer).encode(),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            responses.append(json.load(response))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(responses, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(responses)} decisions in {args.output}")


if __name__ == "__main__":
    main()
