"""Public-data semantics and enforced temporal/frozen experiment boundaries."""
from datetime import datetime
import json
import inspect
import random

import pandas as pd
import pytest

from app.calibration.loaders import NormalizedDeliveryRecord as Record
from app.calibration.profiles import CalibratedProfile, SyntheticProfile
from app.evaluation.freeze import freeze, load_frozen
from app.simulation.generator import generate_shift
from app.strategy.historical import HistoricalDemandModel
from app.strategy.models import StrategyPolicy
from scripts.prepare_public_data import clock_minutes, coordinates
from tests.mvp2_support import config


def test_fractional_clock_and_missing():
    values=clock_minutes(pd.Series(['21:55','0.458333333','1',None,'bad','2']))
    assert values.iloc[:3].tolist()==[1315,660,1440]
    assert values.iloc[3:].isna().all()


def test_invalid_geography_is_not_distance():
    f=pd.DataFrame({'Restaurant_latitude':[20,0,95,-20], 'Restaurant_longitude':[75,0,75,75],
                    'Delivery_location_latitude':[20.01,20,20,-20.01], 'Delivery_location_longitude':[75.01,75,75,75.01]})
    valid,dist,_=coordinates(f)
    assert valid.tolist()==[True,False,False,False]
    assert 1<dist.iloc[0]<2


def test_logistics_survive_missing_payout_and_exposure():
    rows=[Record(timestamp=datetime(2022,1,1,18),pickup_zone=1,distance_km=4,service_time_min=25)]*6
    model=HistoricalDemandModel.fit(rows,hour_exposure=None)
    prediction=model.predict_zone_value(1,datetime(2026,3,21,18),'moto')
    assert prediction.expected_trip_distance==4 and prediction.expected_delivery_time==25
    assert prediction.expected_orders_per_hour is None
    assert prediction.expected_gross_pay is None and prediction.expected_net_pay is None
    assert not prediction.economics_available
    assert prediction.expected_net_mxn_per_hour is None
    assert prediction.sample_count==6
    measured=HistoricalDemandModel.fit(rows,hour_exposure={18:2})
    assert measured.predict_zone_value(1,datetime(2026,3,21,18),'moto').expected_orders_per_hour==3


def test_heldout_changes_cannot_affect_training_or_prediction():
    cutoff=datetime(2022,1,31)
    train=Record(timestamp=datetime(2022,1,1,18),pickup_zone=1,distance_km=4)
    future=Record(timestamp=datetime(2022,2,1,18),pickup_zone=1,distance_km=9999)
    a=HistoricalDemandModel.fit([train,future],hour_exposure=None,training_cutoff=cutoff)
    b=HistoricalDemandModel.fit([train,future.model_copy(update={'distance_km':1})],hour_exposure=None,training_cutoff=cutoff)
    assert a==b
    assert a.predict_zone_value(1,datetime(2026,3,21,18),'moto')==b.predict_zone_value(1,datetime(2026,3,21,18),'moto')
    with pytest.raises(ValueError,match='cutoff'):
        a.predict_zone_value(1,datetime(2021,1,1),'moto')


def test_no_rng_stream_or_shock_input_and_rng_invariance():
    signature=inspect.signature(HistoricalDemandModel.predict_zone_value)
    assert set(signature.parameters)=={'self','zone','sim_time','vehicle'}
    model=HistoricalDemandModel()
    first=model.predict_zone_value(1,datetime(2026,1,1),'moto')
    random.seed(10001)
    for _ in range(100): random.random()
    assert first==model.predict_zone_value(1,datetime(2026,1,1),'moto')


@pytest.mark.parametrize('profile',[SyntheticProfile(),CalibratedProfile()])
def test_both_profiles_deterministic(profile):
    cfg=config().model_copy(update={'profile':profile})
    assert generate_shift(cfg)==generate_shift(cfg)


def test_frozen_config_detects_mutation(tmp_path):
    path=tmp_path/'frozen.json'
    freeze(path,CalibratedProfile(),HistoricalDemandModel(),StrategyPolicy())
    assert load_frozen(path)[2]==StrategyPolicy()
    data=json.loads(path.read_text());data['parameters']['base_reservation_wage']=0
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='hash'):
        load_frozen(path)


def test_empirical_sla_distance_buckets_and_visible_physical_floor():
    from datetime import timedelta
    from app.strategy.models import SLABucket
    from app.strategy.sla import compute_delivery_deadline
    from app.models.requests import DecideRequest
    from tests.mvp2_support import offer
    cfg=config()
    order=DecideRequest.model_validate(offer(cfg,distance_delivery_km=2,estimated_pickup_min=2,estimated_delivery_min=3,restaurant_prep_min=5))
    policy=StrategyPolicy(sla_distance_buckets=(SLABucket(distance_upper_km=3,expected_min=20,p90_min=30,sample_count=100),))
    assert compute_delivery_deadline(order,None,policy)==order.sim_time+timedelta(minutes=30)
    slower=order.model_copy(update={'estimated_delivery_min':45})
    assert compute_delivery_deadline(slower,None,policy)==order.sim_time+timedelta(minutes=52)
    outside=order.model_copy(update={'distance_delivery_km':5})
    assert compute_delivery_deadline(outside,None,policy)==order.sim_time+timedelta(minutes=25)
