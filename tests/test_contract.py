import json
from pathlib import Path

import pytest

from validate_format import PROBE, check_response

ROOT = Path(__file__).resolve().parents[1]


def check_official_properties(body, contract):
    assert set(contract["required"]) <= body.keys()
    for field, spec in contract.get("properties", {}).items():
        if field not in body:
            continue
        value = body[field]
        if "enum" in spec:
            assert value in spec["enum"]
        if spec.get("type") == "number":
            assert isinstance(value, (int, float)) and not isinstance(value, bool)
        if spec.get("type") == "boolean":
            assert isinstance(value, bool)
        if spec.get("type") == "string":
            assert isinstance(value, str)
        if spec.get("type") == "object":
            assert isinstance(value, dict)
            check_official_properties(value, {"required": [], **spec})
        if "maxWords" in spec:
            assert 0 < len(value.split()) < spec["maxWords"]


def test_official_requests_and_response_contract(client):
    schema = json.loads((ROOT / "decision_response_schema.json").read_text())
    events = json.loads((ROOT / "event_log_schema.json").read_text())
    examples = [PROBE, schema["decide_request"]["_illustrative"],
                *events["event_types"]["order_offered"]["_illustrative"]]
    examples += [json.loads(line) for line in (ROOT / "event_log_example.jsonl").read_text().splitlines()
                 if json.loads(line)["event"] == "order_offered"]
    for example in examples:
        response = client.post("/decide", json=example)
        assert response.status_code == 200, response.text
        body = response.json()
        assert not check_response(body, "test")
        check_official_properties(body, schema["decide_response"])
        record = client.get(f"/decisions/{example['order_id']}").json()
        check_official_properties(record, schema["explain_decision_response"])
        assert record["inputs"]["request"] == example
        assert record["alternatives_considered"][0].keys() >= {"option", "rejected_because"}


def test_accept_and_skip(client, payload):
    accept = client.post("/decide", json=payload).json()
    assert accept["decision"] == "ACCEPT"
    assert accept["binding_constraint"] is None
    assert accept["tier"] == "tier1" and accept["degraded"] is False
    payload["base_pay_mxn"] = 0
    payload["est_tip_mxn"] = 0
    skip = client.post("/decide", json=payload).json()
    assert skip["decision"] == "SKIP"
    assert skip["binding_constraint"] == "reservation_wage"


@pytest.mark.parametrize("patch", [
    {"vehicle": "truck"}, {"platform": "other"}, {"event": "shift_start"},
    {"distance_pickup_km": -1}, {"base_pay_mxn": "100"}, {"weight_kg": True},
    {"zone_dropoff": 1.5}, {"surge_multiplier": -1}, {"extra": 1},
    {"sim_time": "not-a-time"}, {"estimated_delivery_min": -1},
    {"courier_state_overrides": {"continuous_riding_min": -1}},
    {"courier_state_overrides": {"in_flight_orders": [{"order_id": "X", "unknown": 1}]}},
    {"courier_state_overrides": {"shift_end_time": "2026-03-21T23:00:00Z"}},
])
def test_invalid_request(client, payload, patch):
    assert client.post("/decide", json={**payload, **patch}).status_code == 422


def test_missing_required_field(client, payload):
    del payload["order_id"]
    assert client.post("/decide", json=payload).status_code == 422


def test_minimal_official_offer_is_valid_but_unknown_load_is_refused(client, payload):
    schema = json.loads((ROOT / "event_log_schema.json").read_text())
    payload["event"] = "order_offered"
    minimal = {key: payload[key] for key in schema["event_types"]["order_offered"]["required"]}
    response = client.post("/decide", json=minimal)
    assert response.status_code == 200
    assert response.json()["binding_constraint"] == "vehicle_capacity"


@pytest.mark.parametrize("field,value", [("base_pay_mxn", "NaN"), ("surge_multiplier", "Infinity")])
def test_nonfinite_rejected(client, payload, field, value):
    text = json.dumps(payload).replace(f'"{field}": {payload[field]}', f'"{field}": {value}')
    response = client.post("/decide", content=text, headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_overflow_is_validation_error(client, payload):
    payload["estimated_delivery_min"] = 1e300
    assert client.post("/decide", json=payload).status_code == 422


def test_unknown_decision(client):
    assert client.get("/decisions/missing").status_code == 404
