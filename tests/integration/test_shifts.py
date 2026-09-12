import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from app.agents.baseline import GreedyRateBaseline
from app.logging.event_log import encode_events, read_events
from app.simulation.config import ShiftConfig, SyntheticConfig
from app.simulation.generator import generate_shift
from app.simulation.replay import logical, replay_shift
from scripts.compare_agents import read_seed_file
from scripts.shift_common import run_pair
from tests.mvp2_support import config, offer, run, selected, shock
from validate_format import check_event_log


@pytest.mark.parametrize("vehicle", ["moto", "car", "bike"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_full_shift_same_offers_independent_execution_and_safety(seed, vehicle):
    cfg = ShiftConfig(seed=seed, shift_hours=8, vehicle=vehicle, start_location_zone=7)
    baseline, smart, comparison = run_pair(cfg)
    assert baseline.stream_sha256 == smart.stream_sha256
    assert selected(baseline, "order_offered") == selected(smart, "order_offered")
    for result in (baseline, smart):
        assert result.state.current_sim_time == cfg.shift_end
        assert result.metrics.orders_offered == result.metrics.orders_accepted + result.metrics.orders_skipped
        assert result.metrics.orders_completed <= result.metrics.orders_accepted
        assert result.metrics.safety_violations == 0
        assert result.metrics.orders_completed > 0
    assert baseline.state is not smart.state
    assert comparison.baseline_safety_violations == comparison.smart_safety_violations == 0


@pytest.mark.parametrize("vehicle", ["moto", "car", "bike"])
def test_no_shocks_no_lateness_or_post_accept_holds(vehicle):
    cfg = ShiftConfig(seed=10, shift_hours=8, vehicle=vehicle, start_location_zone=7,
                      simulation=SyntheticConfig(shock_schedule=()))
    for result in run_pair(cfg)[:2]:
        assert result.metrics.late_deliveries == 0
        assert result.metrics.post_accept_infeasible == 0
        assert result.metrics.uncompleted_orders == 0


@pytest.mark.parametrize("agent", [None, GreedyRateBaseline()])
def test_all_shocks_replay_and_official_validator(tmp_path, agent):
    cfg = config()
    result = run(cfg, offer(cfg),
        shock(cfg, 1, "surge", zone=7, multiplier=2, duration_min=5),
        shock(cfg, 2, "rain", duration_min=5),
        shock(cfg, 3, "closure", zone=7, duration_min=5),
        shock(cfg, 4, "delay", order_id="ONE", slip_min=5),
        offer(cfg, at=5, order_id="TWO"), agent=agent)
    path = tmp_path / "shift.jsonl"
    result.log.write(path)
    errors, counts = check_event_log(str(path))
    assert not errors
    assert counts.keys() >= {"shift_start", "order_offered", "decision", "position_update", "earnings_update", "shock", "shift_end"}
    assert read_events(path) == result.log.events
    replay = replay_shift(path)
    assert replay.full_execution_matches and replay.decisions_checked == 2
    assert replay.stream_sha256 == result.stream_sha256


@pytest.mark.parametrize("tamper", ["reason", "input", "accounting", "source", "missing_decision", "truncate"])
def test_replay_detects_divergence(tmp_path, tamper):
    cfg = config()
    result = run(cfg, offer(cfg))
    events = result.log.events
    decision = next(e for e in events if e["event"] == "decision")
    if tamper == "reason":
        decision["reason"] = "Changed"
    elif tamper == "input":
        decision["decision_request"]["courier_state_overrides"]["continuous_riding_min"] = 240
    elif tamper == "accounting":
        events[-2]["gross_earnings_mxn"] = 999999
    elif tamper == "source":
        next(e for e in events if e["event"] == "order_offered")["source_event"]["base_pay_mxn"] = 0
    elif tamper == "missing_decision":
        events.remove(decision)
    else:
        events.pop()
    path = tmp_path / "bad.jsonl"
    path.write_bytes(encode_events(events))
    with pytest.raises(ValueError):
        replay_shift(path)


def test_replay_ignores_only_latency_variation(tmp_path):
    cfg = config()
    result = run(cfg, offer(cfg))
    for event in selected(result, "decision"):
        event["latency_ms"] += 3
    path = tmp_path / "latency.jsonl"
    result.log.write(path)
    assert replay_shift(path).full_execution_matches


def test_generation_across_fresh_processes_and_hash_seeds():
    code = ("from app.simulation.config import ShiftConfig; "
            "from app.simulation.generator import generate_shift; "
            "from app.logging.event_log import encode_events; "
            "import sys; sys.stdout.buffer.write(encode_events(generate_shift("
            "ShiftConfig(seed=1234,shift_hours=1,vehicle='moto',start_location_zone=7))))")
    first = subprocess.check_output([sys.executable, "-c", code], env={**os.environ, "PYTHONHASHSEED": "1"})
    second = subprocess.check_output([sys.executable, "-c", code], env={**os.environ, "PYTHONHASHSEED": "999"})
    assert first == second


def test_reserved_seeds_disjoint_and_not_default():
    tuning = read_seed_file(Path("config/seeds_tuning.txt"))
    reporting = read_seed_file(Path("config/seeds_reporting.txt"))
    assert len(tuning) >= 10 and len(reporting) >= 10
    assert set(tuning).isdisjoint(reporting)


def test_zero_time_quote_does_not_erase_distance_costs():
    cfg = config()
    result = run(cfg, offer(cfg, estimated_pickup_min=0, estimated_delivery_min=0))
    assert result.metrics.operating_costs_mxn == pytest.approx(3.6)
    assert result.metrics.distance_traveled_km == 3
    assert result.metrics.orders_completed == 1
