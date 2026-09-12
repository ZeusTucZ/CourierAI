"""Fit baseline threshold only. Never change the calibrated simulation profile."""
import argparse
from hashlib import sha256
from math import ceil
from pathlib import Path
from app.agents.nearby import FirstNearbyBaselineConfig
from app.calibration.loaders import load_records
from app.calibration.profiles import SimulationProfile


def derive_threshold(profile,records,*,allow_profile_proxy=False):
    totals=sorted(r.pickup_distance_km+r.distance_km for r in records if r.pickup_distance_km is not None and r.distance_km is not None)
    if totals:
        return FirstNearbyBaselineConfig(max_distance_km=totals[ceil(.75*len(totals))-1],sample_size=len(totals),
            observed_total_sample_size=len(totals),source='data/processed/*_train.jsonl paired distances',profile_version=profile.name,
            classification='derived_historical_paired',transformation='Nearest-rank P75 of paired pickup + delivery training distances')
    if not allow_profile_proxy:
        raise ValueError('No paired historical pickup + delivery distances. Explicit --allow-profile-proxy authorization required; no historical total P75 can be claimed.')
    pickup,delivery=profile.pickup_distance_distribution,profile.order_distance_distribution
    if pickup.kind!='uniform' or delivery.kind!='empirical':
        raise ValueError('Proxy supports existing uniform pickup and empirical delivery profile only')
    values=delivery.values;lo=min(values)+pickup.low;hi=max(values)+pickup.high
    def cdf(x):
        if pickup.high==pickup.low:return sum(v+pickup.low<=x for v in values)/len(values)
        return sum(max(0.,min(1.,(x-v-pickup.low)/(pickup.high-pickup.low))) for v in values)/len(values)
    for _ in range(60):
        mid=(lo+hi)/2
        if cdf(mid)<.75:lo=mid
        else:hi=mid
    return FirstNearbyBaselineConfig(max_distance_km=(lo+hi)/2,sample_size=len(values),observed_total_sample_size=0,
        source='Frozen calibrated profile: empirical delivery training + uniform synthetic pickup',profile_version=profile.name,
        classification='derived_profile_proxy_not_historical_total',transformation='P75 of independent empirical delivery + Uniform(pickup.low,pickup.high); analytic mixture CDF, 60 bisections, no RNG/seeds',
        limitations=('Historical pickup distance absent; sample_size counts delivery observations only, not measured total trips.',
                      'Synthetic pickup and independence assumption; delivery is haversine, not road km.',
                      'Simulator position-to-zone surcharge is excluded from this profile-derived threshold; actual offered total includes it.'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--allow-profile-proxy',action='store_true');args=parser.parse_args()
    profile_path=Path('artifacts/calibrated_profile.json')
    profile=SimulationProfile.load(profile_path)
    records=tuple(r for p in sorted(Path('data/processed').glob('*_train.jsonl')) for r in load_records(p))
    cfg=derive_threshold(profile,records,allow_profile_proxy=args.allow_profile_proxy)
    cfg=cfg.model_copy(update={'source_sha256':sha256(profile_path.read_bytes()).hexdigest()})
    Path('config/first_nearby_baseline.json').write_text(cfg.model_dump_json(indent=2)+'\n')
    print(cfg.model_dump_json(indent=2))


if __name__=='__main__':main()
