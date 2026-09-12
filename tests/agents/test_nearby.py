from datetime import timedelta
import pytest
from app.agents.nearby import FirstNearbyOrderBaseline,FirstNearbyBaselineConfig
from app.models.requests import DecideRequest
from app.models.strategy import StrategySnapshot
from app.simulation.state import CourierState,to_us
from app.calibration.profiles import CalibratedProfile,Distribution
from app.calibration.loaders import NormalizedDeliveryRecord
from scripts.prepare_nearby_baseline import derive_threshold
from tests.mvp2_support import config,offer


@pytest.mark.parametrize('distance,expected',[(3.999,'ACCEPT'),(4.,'ACCEPT'),(4.001,'SKIP')])
def test_nearby_distance_boundary(distance,expected):
    cfg=config();order=DecideRequest.model_validate(offer(cfg,distance_pickup_km=1,distance_delivery_km=distance-1))
    result=FirstNearbyOrderBaseline(FirstNearbyBaselineConfig(max_distance_km=4)).decide(order,CourierState.for_shift(cfg))
    assert result.decision==expected and result.binding_constraint is None and result.economics is None


@pytest.mark.parametrize('constraint,change,continuous',[
 ('flagged_zone_night',{'sim_time':'2026-03-21T22:00:00','zone_dropoff':11},0),
 ('mandatory_break',{},240),('heat_rule',{'sim_time':'2026-03-21T12:00:00'},90),
 ('shift_end_infeasible',{'estimated_delivery_min':70},0),('vehicle_capacity',{'weight_kg':99},0)])
def test_nearby_safety_priority(constraint,change,continuous):
    cfg=config(start=change.get('sim_time','2026-03-21T18:00:00'));state=CourierState.for_shift(cfg)
    state.continuous_riding_us=to_us(continuous)
    order=DecideRequest.model_validate(offer(cfg,distance_pickup_km=.1,distance_delivery_km=.1,**change))
    state.current_sim_time=order.sim_time
    result=FirstNearbyOrderBaseline(FirstNearbyBaselineConfig(max_distance_km=4)).decide(order,state)
    assert result.decision=='SKIP' and result.binding_constraint==constraint and constraint in result.reason


@pytest.mark.parametrize('distance',[2.,5.])
def test_nearby_payment_surge_history_and_wage_invariance(distance):
    cfg=config();state=CourierState.for_shift(cfg)
    order=DecideRequest.model_validate(offer(cfg,distance_pickup_km=1,distance_delivery_km=distance-1))
    snapshots=[StrategySnapshot(),StrategySnapshot(reservation_wage_mxn_hr=9999,zone_values={7:1e6,8:-1e6},economics_v2=True,opportunity_fraction=1,
        zone_predictions={7:{'zone':7,'time_bucket':18,'expected_net_mxn_per_hour':1e6}})]
    results=[]
    for snapshot in snapshots:
        agent=FirstNearbyOrderBaseline(FirstNearbyBaselineConfig(max_distance_km=4),snapshot)
        for pay in (20,500):
            for surge in (1.,3.):
                response=agent.decide(order.model_copy(update={'base_pay_mxn':pay,'est_tip_mxn':pay,'surge_multiplier':surge}),state)
                results.append((response.decision,response.reason,response.binding_constraint))
    assert len(set(results))==1


def test_nearby_deterministic_without_prediction_access(monkeypatch):
    from app.strategy.historical import HistoricalDemandModel
    def forbidden(*a,**kw):raise AssertionError('Historical prediction used')
    monkeypatch.setattr(HistoricalDemandModel,'predict_zone_value',forbidden)
    cfg=config();state=CourierState.for_shift(cfg);order=DecideRequest.model_validate(offer(cfg))
    agent=FirstNearbyOrderBaseline(FirstNearbyBaselineConfig(max_distance_km=4))
    a,b=agent.decide(order,state),agent.decide(order,state)
    assert a.model_dump(exclude={'latency_ms'})==b.model_dump(exclude={'latency_ms'})


def test_missing_paired_data_requires_explicit_proxy():
    with pytest.raises(ValueError,match='No paired historical'):
        derive_threshold(CalibratedProfile(),[NormalizedDeliveryRecord(distance_km=3)])


def test_paired_p75_does_not_add_unpaired_values():
    rows=[NormalizedDeliveryRecord(pickup_distance_km=1,distance_km=n) for n in (1,2,3,4)]
    rows.append(NormalizedDeliveryRecord(distance_km=10000))
    c=derive_threshold(CalibratedProfile(),rows)
    assert c.max_distance_km==4 and c.sample_size==4 and c.observed_total_sample_size==4


def test_proxy_exact_cdf_quantile_no_rng():
    profile=CalibratedProfile(pickup_distance_distribution=Distribution(low=0,high=4),order_distance_distribution=Distribution(kind='empirical',values=(10,)))
    c=derive_threshold(profile,[],allow_profile_proxy=True)
    assert c.max_distance_km==pytest.approx(13) and c.observed_total_sample_size==0


def test_nearby_runner_no_strategic_actions_and_replay(tmp_path):
    from app.evaluation.runner import run_pair_v3
    from app.strategy.historical import HistoricalDemandModel
    from app.strategy.models import StrategyPolicy
    from scripts.compare_nearby_baseline import validate_nearby_log
    cfg=config(hours=2)
    policy=StrategyPolicy()
    before=policy.model_dump()
    baseline,smart=run_pair_v3(cfg,HistoricalDemandModel(),policy,output=tmp_path,
        baseline_config=FirstNearbyBaselineConfig(max_distance_km=4))
    assert baseline.agent_name=='FirstNearbyOrderBaseline'
    assert baseline.metrics.reposition_count==0 and baseline.metrics.orders_cancelled==0
    assert baseline.metrics.safety_violations==smart.metrics.safety_violations==0
    assert policy.model_dump()==before
    assert smart.log.events[0]['strategy_policy']==policy.model_dump(mode='json')
    assert not any(e['event']=='strategy_update' for e in baseline.log.events)
    assert baseline.stream_sha256==smart.stream_sha256
    validate_nearby_log(tmp_path/f'seed-{cfg.seed}/FirstNearbyOrderBaseline.jsonl')
