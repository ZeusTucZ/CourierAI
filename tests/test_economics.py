import pytest

from app.models.strategy import StrategySnapshot


def test_arithmetic(evaluate):
    economics = evaluate().economics
    assert economics.gross_pay_mxn == 110
    assert economics.operating_cost_mxn == pytest.approx(3.6)
    assert economics.net_pay_mxn == pytest.approx(106.4)
    assert economics.total_time_min == 10
    assert economics.raw_rate_mxn_hr == pytest.approx(638.4)
    assert economics.adjusted_rate_mxn_hr == pytest.approx(653.4)
    assert economics.deadhead_km == 1


def test_surge_only_multiplies_base(evaluate):
    assert evaluate({"surge_multiplier": 2}).economics.gross_pay_mxn == 210


def test_distance_increases_cost(evaluate):
    assert evaluate({"distance_delivery_km": 10}).economics.operating_cost_mxn > evaluate().economics.operating_cost_mxn


def test_vehicle_profiles_affect_cost_and_derived_time(evaluate):
    results = [evaluate({"vehicle": vehicle, "estimated_pickup_min": None,
                         "estimated_delivery_min": None}).economics for vehicle in ("moto", "car", "bike")]
    assert len({result.total_time_min for result in results}) == 3
    assert len({result.operating_cost_mxn for result in results}) == 3


def test_prep_and_partial_estimates(evaluate):
    economics = evaluate({"estimated_delivery_min": None, "restaurant_prep_min": 9}).economics
    assert economics.total_time_min == pytest.approx(5 + 9 + 2 / 25 * 60)


@pytest.mark.parametrize("wage_delta,decision", [(-.000001, "ACCEPT"), (0, "ACCEPT"), (.000001, "SKIP")])
def test_exact_reservation_threshold(evaluate, wage_delta, decision):
    rate = evaluate().economics.adjusted_rate_mxn_hr
    result = evaluate(strategy=StrategySnapshot(reservation_wage_mxn_hr=rate + wage_delta))
    assert result.decision == decision
    assert result.binding_constraint == (None if decision == "ACCEPT" else "reservation_wage")
    if wage_delta:
        assert repr(rate) in result.reason
        assert repr(rate + wage_delta) in result.reason


def test_dropoff_value_changes_decision(evaluate):
    strategy = StrategySnapshot(reservation_wage_mxn_hr=650, zone_values={7: 20, 11: -20})
    good = evaluate({"zone_dropoff": 7}, strategy)
    bad = evaluate({"zone_dropoff": 11}, strategy)
    assert good.economics.raw_rate_mxn_hr == bad.economics.raw_rate_mxn_hr
    assert good.decision == "ACCEPT" and bad.decision == "SKIP"


def test_unknown_zone_has_zero_adjustment(evaluate):
    result = evaluate({"zone_dropoff": 999}).economics
    assert result.adjusted_rate_mxn_hr == result.raw_rate_mxn_hr


def test_zero_duration_uses_configured_floor(evaluate, snapshot):
    result = evaluate({"distance_pickup_km": 0, "distance_delivery_km": 0,
                       "estimated_pickup_min": 0, "estimated_delivery_min": 0})
    assert result.economics.total_time_min == snapshot.policy.minimum_service_time_min
