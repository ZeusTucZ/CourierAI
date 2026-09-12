"""Read-only diagnostics against frozen calibration; never refits heldout records."""
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from app.calibration.loaders import load_records
from app.evaluation.freeze import load_frozen
from app.strategy.models import StrategyPolicy


def main():
    out=Path('artifacts')
    frozen=out/'final_strategy_config.json'; before=sha256(frozen.read_bytes()).hexdigest()
    profile,model,policy=load_frozen(frozen)
    training=load_records(Path('data/processed/zomato_train.jsonl'))
    heldout=load_records(Path('data/processed/zomato_heldout.jsonl'))
    assert max(r.timestamp for r in training)<min(r.timestamp for r in heldout)
    counts=Counter(r.timestamp.hour for r in training)
    pickups=Counter(r.pickup_zone for r in training if r.pickup_zone is not None)
    dropoffs=Counter(r.dropoff_zone for r in training if r.dropoff_zone is not None)
    transitions=[{'pickup':f'zone_{t.pickup}','dropoff':f'zone_{t.dropoff}', 'count':t.count,
                  'probability_given_pickup':t.count/pickups[t.pickup]} for t in profile.zone_transition_distribution]
    evidence={'hour_frequency':dict(sorted(counts.items())), 'hour_share':{h:n/len(training) for h,n in sorted(counts.items())},
              'pickup_density_share':{f'zone_{z}':n/sum(pickups.values()) for z,n in sorted(pickups.items())},
              'dropoff_density_share':{f'zone_{z}':n/sum(dropoffs.values()) for z,n in sorted(dropoffs.items())},
              'transitions':transitions,'relative_attractiveness':'pickup density share; descriptive, not earnings',
              'limitations':'Observed sample shares are not exposure-adjusted demand rates. No real Monterrey names/geography.'}
    (out/'demand_structure.json').write_text(json.dumps(evidence,indent=2)+'\n')
    coverage=[];low=0
    for b in policy.sla_distance_buckets:
        rows=[r for r in heldout if r.distance_km is not None and low<r.distance_km<=b.distance_upper_km and r.service_time_min is not None]
        coverage.append({'distance_low_km':low,'distance_high_km':b.distance_upper_km,'n':len(rows),
                         'p90_training_min':b.p90_min,'heldout_coverage':sum(r.service_time_min<=b.p90_min for r in rows)/len(rows) if rows else None})
        low=b.distance_upper_km
    result={'status':'PASS','strict_temporal_separation':True,'training_count':len(training),'heldout_count':len(heldout),
            'sla_heldout_coverage':coverage,'limitations':'Read-only retrospective coverage, no threshold updates. Future simulation seeds remain separate.'}
    audit=json.loads((out/'data_audit_report.json').read_text())
    assert all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in audit['raw_sha256'].items())
    result['raw_hashes_unchanged']=True
    assert before==sha256(frozen.read_bytes()).hexdigest()
    result['frozen_sha256_unchanged']=before
    (out/'public_data_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
