"""MVP 3 behavioral checks; all data in this file is explicitly synthetic."""
import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

import pytest
from pydantic import ValidationError

from app.agents.smart import SmartAgent
from app.calibration.fitting import calibrate
from app.calibration.loaders import NormalizedDeliveryRecord, load_records, load_solomon
from app.calibration.profiles import CalibratedProfile, Distribution, SimulationProfile
from app.evaluation.runner import ABLATIONS, enforce_safety, evaluate, seed_sets, validate_training, variant
from app.logging.event_log import encode_events
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.services.strategy_store import StrategyStore
from app.simulation.generator import generate_shift
from app.simulation.replay import replay_shift, logical
from app.simulation.strategic import StrategicSimulator
from app.strategy.cancellation import CancellationPolicy
from app.strategy.historical import HistoricalDemandModel, DemandBucket
from app.strategy.models import StrategyPolicy, ZonePrediction
from app.strategy.opportunity_cost import opportunity_cost
from app.strategy.reposition import choose_reposition
from app.strategy.sla import compute_delivery_deadline
from app.strategy.updater import StrategyUpdater
from tests.mvp2_support import config, offer, shock, stream, selected
from validate_format import check_event_log


def demand():
    return HistoricalDemandModel(buckets=(
        DemandBucket(zone=7, hour=18, orders_per_hour=1, gross_pay=20, distance_km=2, service_min=10, sample_count=20),
        DemandBucket(zone=8, hour=18, orders_per_hour=6, gross_pay=200, distance_km=2, service_min=10, sample_count=20)),
        trained_through=datetime(2026, 2, 1), training_seeds=(1,), source="synthetic fixture")


def policy(**changes):
    return StrategyPolicy.model_validate({**StrategyPolicy().model_dump(),
        "base_reservation_wage": 0, "min_reservation_wage": 0, "max_reservation_wage": 0,
        "use_reposition": False, "opportunity_fraction": 0, **changes})


def run3(cfg, *events, settings=None, model=None, unavailable=()):
    sim = StrategicSimulator(cfg, SmartAgent(), model or HistoricalDemandModel(), settings or policy(), unavailable_updates=unavailable)
    result = sim.run(stream(cfg, *events))
    return result, sim


def test_profile_roundtrip_and_deep_immutability(tmp_path):
    profile = CalibratedProfile(order_distance_distribution=Distribution(kind="empirical", values=(1, 2, 3)))
    path = tmp_path / "profile.json"
    profile.save(path)
    assert SimulationProfile.load(path) == SimulationProfile.model_validate(profile.model_dump())
    with pytest.raises(ValidationError):
        profile.orders_per_hour = 100
    with pytest.raises(ValidationError):
        profile.order_distance_distribution.values = (999,)


@pytest.mark.parametrize("suffix", [".csv", ".json", ".jsonl"])
def test_dataset_column_mapping_and_missingness(tmp_path, suffix):
    path = tmp_path / ("deliveries" + suffix)
    rows = [{"km": 4, "pay": 50}, {"km": 6, "pay": None}]
    path.write_text("km,pay\n4,50\n6,\n" if suffix == ".csv" else json.dumps(rows) if suffix == ".json" else "\n".join(json.dumps(r) for r in rows))
    records = load_records(path, {"distance_km": "km", "base_pay_mxn": "pay"})
    assert records[0].timestamp is None and records[1].base_pay_mxn is None
    profile, report = calibrate(records, source=str(path))
    assert profile.order_distance_distribution.values == (4, 6)
    assert report["missingness"]["base_pay_mxn"] == .5
    assert report["orders_per_hour"] is None
    assert next(p for p in profile.provenance if p.parameter == "orders_per_hour").fallback


def test_solomon_preserves_unknown_units(tmp_path):
    path = tmp_path / "c101.txt"
    path.write_text("CUSTOMER\n0 40 50 0 0 1000 0\n1 45 55 10 5 100 90\n")
    assert load_solomon(path)[0].demand_weight is None
    converted = load_solomon(path, demand_to_kg=.1, service_to_minutes=1)[0]
    assert converted.demand_weight == 1 and converted.service_time_min == 90
    assert converted.timestamp is None and converted.distance_km is None


def test_calibrated_generation_byte_identical():
    cfg = config().model_copy(update={"profile": CalibratedProfile(order_distance_distribution=Distribution(kind="empirical", values=(2, 7)))})
    first = generate_shift(cfg)
    assert encode_events(first) == encode_events(generate_shift(cfg))
    assert {e["distance_delivery_km"] for e in first if e["event"] == "order_offered"} <= {2, 7}
    assert encode_events(first) != encode_events(generate_shift(cfg.model_copy(update={"seed": 99})))


def test_historical_zone_hour_deterministic_and_sparse_fallback():
    model = demand()
    when = datetime(2026, 3, 21, 18)
    low, high = [model.predict_zone_value(zone, when, "moto") for zone in (7, 8)]
    assert high.expected_net_mxn_per_hour > low.expected_net_mxn_per_hour
    assert high == model.predict_zone_value(8, when, "moto")
    assert model.predict_zone_value(99, when, "moto").fallback
    assert model.predict_zone_value(8, when.replace(hour=19), "moto").fallback


def test_future_leakage_is_prevented_by_cutoff_and_model_interface():
    model = demand()
    with pytest.raises(ValueError, match="cutoff"):
        model.predict_zone_value(7, datetime(2026, 1, 1), "moto")
    cfg = config()
    common = offer(cfg, base_pay_mxn=100)
    settings = policy()
    left, _ = run3(cfg, common, offer(cfg, at=10, order_id="FUTURE", base_pay_mxn=0), model=model, settings=settings)
    right, _ = run3(cfg, common, shock(cfg, 10, "rain", duration_min=20),
                    offer(cfg, at=20, order_id="DIFFERENT", base_pay_mxn=10000), model=model, settings=settings)
    assert logical(selected(left, "strategy_update")[0]) == logical(selected(right, "strategy_update")[0])
    assert logical(selected(left, "decision")[0]) == logical(selected(right, "decision")[0])


def test_historical_fit_requires_exposure_and_excludes_missing_economics():
    rows = (NormalizedDeliveryRecord(timestamp=datetime(2026, 1, 1, 18), pickup_zone=7),)
    with pytest.raises(ValueError, match="exposure"):
        HistoricalDemandModel.fit(rows, hour_exposure={})
    assert not HistoricalDemandModel.fit(rows, hour_exposure={18: 1}).buckets


def test_snapshot_update_clipping_and_immutability():
    store = StrategyStore(StrategySnapshot())
    updater = StrategyUpdater(demand(), StrategyPolicy(zone_value_clip=10), (7, 8))
    before = store.get()
    updated = updater.update(store, datetime(2026, 3, 1, 18), "moto", 120)
    assert updated is not before and before.zone_predictions == {}
    assert set(updated.zone_values.values()) == {-10, 10}
    assert updated.target_zone == 8
    with pytest.raises(TypeError):
        updated.zone_predictions[7] = updated.zone_predictions[8]


@pytest.mark.parametrize("remaining", [0, 1, 59, 60, 480])
def test_reservation_wage_bounds(remaining):
    store = StrategyStore(StrategySnapshot())
    settings = StrategyPolicy(min_reservation_wage=100, max_reservation_wage=170)
    snapshot = StrategyUpdater(demand(), settings, (7, 8)).update(store, datetime(2026, 3, 1, 18), "moto", remaining)
    assert 100 <= snapshot.reservation_wage_mxn_hr <= 170


def test_failure_keeps_last_snapshot_fast_path_and_recovers():
    agent = SmartAgent()
    updater = StrategyUpdater(demand(), StrategyPolicy(), (7, 8))
    when = datetime(2026, 3, 21, 18)
    good = updater.update(agent.service.strategies, when, "moto", 120)
    stale = updater.update(agent.service.strategies, when + timedelta(minutes=1), "moto", 119, available=False)
    assert stale.zone_values == good.zone_values and stale.reservation_wage_mxn_hr == good.reservation_wage_mxn_hr
    response = agent.decide_request(DecideRequest.model_validate(offer(config())))
    assert response.degraded and response.latency_ms < 50
    updater.update(agent.service.strategies, when + timedelta(minutes=2), "moto", 118)
    assert not agent.decide_request(DecideRequest.model_validate(offer(config()))).degraded


@pytest.mark.parametrize("rate,minutes,expected", [(0, 60, 0), (10, 30, 5), (200, 30, 100), (200, 60, 200)])
def test_opportunity_cost(rate, minutes, expected):
    assert opportunity_cost(rate, minutes) == expected


def test_reposition_gain_dwell_and_deterministic_target():
    cfg = config()
    from app.simulation.state import CourierState
    state = CourierState.for_shift(cfg)
    store = StrategyStore(StrategySnapshot())
    snapshot = StrategyUpdater(demand(), StrategyPolicy(), (7, 8)).update(store, state.current_sim_time, "moto", 60)
    action = choose_reposition(state, snapshot, StrategyPolicy())
    assert action.zone == 8 and action.gain_mxn > 0
    assert action == choose_reposition(state, snapshot, StrategyPolicy())
    assert choose_reposition(state, snapshot, StrategyPolicy(minimum_reposition_gain=10000)) is None
    assert choose_reposition(state, snapshot, StrategyPolicy(), state.current_sim_time) is None


def test_reposition_executes_and_charges_cost_distance_time():
    cfg = config()
    result, sim = run3(cfg, offer(cfg, at=10, base_pay_mxn=0, est_tip_mxn=0),
                       settings=policy(use_reposition=True), model=demand())
    assert result.metrics.reposition_count >= 1
    assert result.metrics.reposition_distance_km > 0
    assert result.metrics.reposition_cost_mxn == pytest.approx(result.metrics.reposition_distance_km * 1.2)
    assert result.metrics.net_earnings_mxn == pytest.approx(result.metrics.gross_earnings_mxn - result.metrics.operating_costs_mxn)
    assert any(e["type"] == "reposition_completed" for e in sim.trace)
    assert result.metrics.safety_violations == 0


def test_insertion_beats_fifo_and_preserves_pickup_capacity_sla():
    cfg = config()
    events = (offer(cfg, order_id="A", estimated_pickup_min=5, estimated_delivery_min=20),
              offer(cfg, at=2, order_id="B", estimated_pickup_min=1, estimated_delivery_min=1))
    settings = policy(sla_time_multiplier=1, sla_buffer_min=5)
    full, _ = run3(cfg, *events, settings=settings)
    fifo, _ = run3(cfg, *events, settings=settings.model_copy(update={"use_improved_batching": False}))
    assert selected(full, "decision")[1]["decision"] == "ACCEPT"
    assert selected(fifo, "decision")[1]["decision"] == "SKIP"
    assert full.metrics.orders_completed == 2 and fifo.metrics.orders_completed == 1
    assert full.metrics.late_deliveries == full.metrics.safety_violations == 0
    positions = selected(full, "position_update")
    for ident in ("A", "B"):
        pickup = next(i for i, e in enumerate(positions) if e.get("order_id") == ident and e.get("action") == "pickup_arrival")
        delivery = next(i for i, e in enumerate(positions) if e.get("order_id") == ident and e.get("action") == "dropoff_arrival")
        assert pickup < delivery
    assert all(e["current_weight_kg"] <= 15 and e["current_volume_liters"] <= 50 for e in positions)


def test_batching_rejects_capacity_and_sla_and_has_bounded_latency():
    cfg = config()
    result, _ = run3(cfg, offer(cfg, weight_kg=15), offer(cfg, at=1, order_id="B", weight_kg=1))
    assert selected(result, "decision")[1]["binding_constraint"] == "vehicle_capacity"
    assert max(e["latency_ms"] for e in selected(result, "decision")) < 50
    with pytest.raises(ValidationError):
        StrategyPolicy(max_active_orders=1000)
    with pytest.raises(ValidationError):
        StrategyPolicy(max_insertions=1000)


def test_sla_fixed_at_acceptance_and_shock_lateness():
    cfg = config()
    order = DecideRequest.model_validate(offer(cfg))
    assert compute_delivery_deadline(order, None, policy(sla_time_multiplier=1.5, sla_buffer_min=10)) == order.sim_time + timedelta(minutes=25)
    result, _ = run3(cfg, offer(cfg), shock(cfg, 2, "delay", order_id="ONE", slip_min=20), settings=policy(use_cancellation=False))
    completion = next(e for e in selected(result, "earnings_update") if e.get("completed_order_id"))
    assert completion["promised_completion_time"].endswith("18:25:00")
    assert completion["late"] and completion["disruption_caused_lateness"]
    assert selected(result, "decision")[0]["decision"] == "ACCEPT"


@pytest.mark.parametrize("kind", [None, "surge", "closure", "rain", "delay"])
def test_cancellation_guardrails(kind):
    choice = CancellationPolicy(policy()).evaluate(triggering_shock=None if kind is None else {"shock_type": kind},
        remaining_net=10, remaining_min=60, lateness_min=100, expected_rate=0)
    assert choice.cancel == (kind in {"closure", "rain", "delay"})


def test_continue_when_cancellation_cost_is_worse():
    choice = CancellationPolicy(policy(cancellation_penalty_mxn=1000)).evaluate(triggering_shock={"shock_type": "delay"},
        remaining_net=100, remaining_min=10, lateness_min=1, expected_rate=0)
    assert not choice.cancel


def test_cancellation_execution_penalties_and_no_prepayment():
    cfg = config(hours=3)
    result, sim = run3(cfg, offer(cfg, base_pay_mxn=100, est_tip_mxn=0),
                       shock(cfg, 2, "delay", order_id="ONE", slip_min=100),
                       settings=policy(cancellation_penalty_mxn=7, lateness_penalty_mxn_per_min=3))
    assert result.metrics.orders_cancelled == 1 and result.metrics.orders_completed == 0
    assert result.metrics.gross_earnings_mxn == 0
    assert result.metrics.cancellation_penalties_mxn == 7
    assert result.metrics.net_earnings_mxn == pytest.approx(-7 - result.metrics.operating_costs_mxn)
    assert any(e.get("cancel") and e.get("triggering_shock") for e in sim.trace)


def test_skip_and_cancellation_penalties_are_separate():
    cfg = config()
    result, _ = run3(cfg, offer(cfg, weight_kg=99), settings=policy(skip_penalty_mxn=3, cancellation_penalty_mxn=7))
    assert result.metrics.skip_penalties_mxn == 3
    assert result.metrics.cancellation_penalties_mxn == 0
    assert result.metrics.net_earnings_mxn == -3


def test_tuning_heldout_overlap_and_calibration_leakage_fail(tmp_path):
    train, heldout = tmp_path / "train", tmp_path / "heldout"
    train.write_text("1\n2\n")
    heldout.write_text("2\n3\n")
    with pytest.raises(ValueError, match="overlap"):
        seed_sets(train, heldout)
    with pytest.raises(ValueError, match="heldout"):
        validate_training(CalibratedProfile(training_seeds=(10001,)), HistoricalDemandModel(), [1], [10001])


def test_ten_shifts_configs_frozen_and_csv_shape(tmp_path):
    profile = CalibratedProfile(orders_per_hour=2)
    model, settings = HistoricalDemandModel(), policy()
    frozen = [m.model_dump(mode="json") for m in (profile, model, settings)]
    # Development seeds only. Final heldout set is not consumed by tests.
    result = evaluate(list(range(201, 211)), profile, model, settings, output=tmp_path, hours=.1)
    assert result["shifts"] == 10 and result["safety_violations"] == 0
    assert [m.model_dump(mode="json") for m in (profile, model, settings)] == frozen
    assert (tmp_path / "results_mvp3.csv").read_text().splitlines()[0] == next(line for line in Path("results_table_template.csv").read_text().splitlines() if line.startswith("policy,"))


def test_safety_violation_fails_evaluation():
    result, _ = run3(config(), offer(config()))
    result.metrics = replace(result.metrics, safety_violations=1)
    with pytest.raises(ValueError, match="FAILED safety"):
        enforce_safety([result])


@pytest.mark.parametrize("name", ABLATIONS)
def test_ablation_changes_only_named_feature(name):
    base = StrategyPolicy()
    changed = variant(base, name)
    difference = {key: value for key, value in changed.model_dump().items() if value != base.model_dump()[key]}
    assert difference == ABLATIONS[name]


def test_replay_updates_failure_recovery_and_official_log(tmp_path):
    cfg = config(hours=2)
    events = (offer(cfg, order_id="A"), offer(cfg, at=31, order_id="B"), offer(cfg, at=61, order_id="C"))
    result, sim = run3(cfg, *events, model=demand(), unavailable=(1,))
    assert [e["degraded"] for e in selected(result, "decision")] == [False, True, False]
    path = tmp_path / "shift.jsonl"
    result.log.write(path)
    assert not check_event_log(str(path))[0]
    assert replay_shift(path).full_execution_matches
    again, repeat = run3(cfg, *events, model=demand(), unavailable=(1,))
    assert sim.trace == repeat.trace
    assert logical(result.log.events) == logical(again.log.events)


def test_replay_rejects_tampered_strategy_update(tmp_path):
    result, _ = run3(config(), offer(config()), model=demand())
    selected(result, "strategy_update")[0]["snapshot"]["zone_values"]["7"] = 10000
    path = tmp_path / "bad.jsonl"
    result.log.write(path)
    with pytest.raises(ValueError, match="mismatch"):
        replay_shift(path)


def test_legacy_mvp2_log_replays_without_new_optional_fields(tmp_path):
    from tests.mvp2_support import run
    result = run(config(), offer(config()))
    metadata = result.log.events[0]
    metadata["simulation_config"].pop("profile")
    for field in ("strategy_version", "generated_at_sim_time", "target_zone", "zone_predictions",
                  "economics_v2", "opportunity_fraction", "skip_penalty_mxn"):
        metadata["strategy_snapshot"].pop(field)
    economics = selected(result, "decision")[0]["economics"]
    assert "opportunity_cost_mxn" not in economics
    path = tmp_path / "legacy.jsonl"
    result.log.write(path)
    assert replay_shift(path).full_execution_matches


@pytest.mark.parametrize("vehicle", ["moto", "car", "bike"])
def test_strategic_execution_safety_all_vehicles(vehicle):
    cfg = config(vehicle=vehicle, hours=2)
    result, _ = run3(cfg, offer(cfg), offer(cfg, at=5, order_id="B"),
                     shock(cfg, 6, "rain", duration_min=20), model=demand())
    assert result.metrics.safety_violations == 0
    assert result.state.current_sim_time == cfg.shift_end


def test_v2_fast_path_does_not_read_history_or_files(monkeypatch):
    store = StrategyStore(StrategySnapshot())
    snapshot = StrategyUpdater(demand(), StrategyPolicy(), (7, 8)).update(store, datetime(2026, 3, 21, 18), "moto", 60)
    agent = SmartAgent(snapshot)
    request = DecideRequest.model_validate(offer(config()))
    def forbidden(*args, **kwargs):
        raise AssertionError("Dataset or prediction accessed from fast path")
    monkeypatch.setattr(HistoricalDemandModel, "predict_zone_value", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    assert agent.decide_request(request).latency_ms < 50


def test_disruption_attribution_propagates_to_queued_order():
    cfg = config()
    result, _ = run3(cfg, offer(cfg, order_id="A"), offer(cfg, at=1, order_id="B"),
        shock(cfg, 2, "delay", order_id="A", slip_min=20), settings=policy(use_cancellation=False))
    completions = {e["completed_order_id"]: e for e in selected(result, "earnings_update") if e.get("completed_order_id")}
    assert completions["B"]["late"] and completions["B"]["disruption_caused_lateness"]
