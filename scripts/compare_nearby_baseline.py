"""Baseline replacement, NOT Smart tuning. Preserve old streams/results and freeze."""
import argparse
import csv
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from statistics import mean
from app.agents.nearby import FirstNearbyBaselineConfig,FirstNearbyOrderBaseline
from app.evaluation.freeze import load_frozen
from app.evaluation.runner import evaluate,seed_sets,validate_training
from app.models.strategy import StrategySnapshot
from app.simulation.config import ShiftConfig
from app.simulation.replay import logical,replay_shift
from app.simulation.strategic import StrategicSimulator
from app.strategy.historical import HistoricalDemandModel
from app.strategy.models import StrategyPolicy
from validate_format import check_event_log

OUT=Path('artifacts/nearby_baseline')
HARD={'flagged_zone_night','mandatory_break','heat_rule','shift_end_infeasible','vehicle_capacity'}


def events(path):return [json.loads(l) for l in path.read_text().splitlines()]


def quantile(values,p):
    values=sorted(values)
    if not values:return None
    pos=(len(values)-1)*p;lo=int(pos);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(pos-lo)


def csv_write(path,rows):
    with path.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def validate_nearby_log(path):
    original=events(path);meta=original[0]
    simulator=StrategicSimulator(ShiftConfig.model_validate(meta['simulation_config']),
        FirstNearbyOrderBaseline(FirstNearbyBaselineConfig.model_validate(meta['baseline_config']),StrategySnapshot.model_validate(meta['strategy_snapshot'])),
        HistoricalDemandModel.model_validate(meta['historical_model']),StrategyPolicy.model_validate(meta['strategy_policy']),
        unavailable_updates=meta['unavailable_updates'])
    replay=simulator.run([e['source_event'] for e in original if 'source_event' in e])
    replay.log.events[0]['baseline_config']=meta['baseline_config']
    assert logical(replay.log.events)==logical(original),'Baseline replay mismatch'
    assert not replay.metrics.safety_violations


def run_mode(mode,profile,model,policy,baseline,seeds):
    output=Path(f'evaluation/{mode}_nearby_results')
    try:result=evaluate(seeds,profile,model,policy,output=output,baseline_config=baseline)
    except Exception as exc:
        output.mkdir(parents=True,exist_ok=True);(output/'FAILED.json').write_text(json.dumps({'status':'FAILED','cause':str(exc)}));raise
    prior=Path('evaluation/heldout_results') if mode=='heldout' else Path('evaluation/ablation_results/SmartFull')
    old=json.loads((prior/'results.json').read_text())
    assert [r['seed'] for r in old['rows']]==seeds
    comparisons=[];actions=[];distances=[];skip=Counter();validation=[];secondary=[]
    for row in result['rows']:
        seed=row['seed'];b,s=row['baseline'],row['smart']
        previous=next(r for r in old['rows'] if r['seed']==seed)
        assert logical(s)==logical(previous['smart']),'Smart changed non-latency results'
        oldsmart=events(prior/f'seed-{seed}/SmartAgent.jsonl')
        smartpath=output/f'seed-{seed}/SmartAgent.jsonl'
        assert logical(events(smartpath))==logical(oldsmart),'Smart stream/state/decisions changed'
        basepath=output/f'seed-{seed}/FirstNearbyOrderBaseline.jsonl'
        baseline_events=events(basepath)
        assert baseline_events[0]['stream_sha256']==oldsmart[0]['stream_sha256']
        for path in (basepath,smartpath):
            errors,_=check_event_log(str(path))
            validation.append({'path':str(path),'format_errors':errors})
        validate_nearby_log(basepath);replay_shift(smartpath)
        for e in baseline_events:
            if e['event']!='decision':continue
            distance=e['decision_request']['distance_pickup_km']+e['decision_request']['distance_delivery_km']
            if e['decision']=='ACCEPT':category='ACCEPT';distances.append(distance)
            elif e['binding_constraint'] in HARD:category=e['binding_constraint']
            elif e['reason'].startswith('Skipped: total distance'):category='distance'
            else:category='simulator_feasibility_gate'
            skip[category]+=1
            actions.append({'seed':seed,'order_id':e['order_id'],'decision':e['decision'],'category':category,'distance_total_km':distance,'threshold_km':baseline.max_distance_km,'reason':e['reason']})
        comparisons.append({'seed':seed,'FirstNearbyOrderBaseline_net':b['net_earnings_mxn'],'SmartAgent_net':s['net_earnings_mxn'],
            'difference':s['net_earnings_mxn']-b['net_earnings_mxn'],'improvement_pct':row['improvement_pct'],
            'baseline_accepted':b['orders_accepted'],'baseline_skipped':b['orders_skipped'],'smart_accepted':s['orders_accepted'],'smart_skipped':s['orders_skipped']})
        secondary.append({'seed':seed,'FirstNearbyOrderBaseline':b['net_earnings_mxn'],'GreedyRateBaseline':previous['baseline']['net_earnings_mxn'],'SmartAgent':s['net_earnings_mxn']})
    offers=len(actions)
    totals={agent:{key:sum(r[agent][key] for r in result['rows']) for key in ('orders_completed','late_deliveries','distance_traveled_km','safety_violations','orders_cancelled','reposition_count')} for agent in ('baseline','smart')}
    assert totals['baseline']['reposition_count']==0
    report={k:v for k,v in result.items() if k!='rows'}
    report.update(experiment='Baseline replacement only; Smart frozen, no retuning; previously used heldout streams reused for comparison',
        baseline_config=baseline.model_dump(mode='json'),totals=totals,offers=offers,skip_counts=dict(skip),
        accepted_pct=skip['ACCEPT']/offers*100,distance_skip_pct=skip['distance']/offers*100,
        hard_constraint_skip_pct=sum(skip[k] for k in HARD)/offers*100,
        simulator_gate_skip_pct=skip['simulator_feasibility_gate']/offers*100,
        accepted_distance={'n':len(distances),'mean':mean(distances) if distances else None,'p50':quantile(distances,.5),'p75':quantile(distances,.75),'p95':quantile(distances,.95)},
        secondary_means={a:mean(r[a] for r in secondary) for a in ('FirstNearbyOrderBaseline','GreedyRateBaseline','SmartAgent')},
        smart_identical_to_previous=True,source_streams_identical_to_previous=True,
        log_validation_status='PASS' if not any(r['format_errors'] for r in validation) else 'FAILED_FORMAT',replay_status='PASS')
    for name,rows in [('comparison',comparisons),('decisions',actions),('secondary_comparison',secondary)]:csv_write(OUT/f'{mode}_{name}.csv',rows)
    (OUT/f'{mode}_summary.json').write_text(json.dumps(report,indent=2)+'\n')
    (OUT/f'{mode}_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return report


def main(mode_override=None):
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('tuning','heldout','both'),default=mode_override or 'both');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    frozen=Path('artifacts/final_strategy_config.json');before=sha256(frozen.read_bytes()).hexdigest()
    profile,model,policy=load_frozen(frozen);baseline=FirstNearbyBaselineConfig.load()
    assert baseline.profile_version==profile.name
    tuning,heldout=seed_sets();validate_training(profile,model,tuning,heldout)
    if args.mode in ('tuning','both'):run_mode('tuning',profile,model,policy,baseline,tuning)
    if args.mode in ('heldout','both'):
        pre=json.loads((OUT/'tuning_summary.json').read_text())
        assert pre['status']=='PASS' and pre['baseline_config']==baseline.model_dump(mode='json')
        assert pre['frozen_config_sha256']==json.loads(frozen.read_text())['experiment_sha256']
        run_mode('heldout',profile,model,policy,baseline,heldout)
    assert sha256(frozen.read_bytes()).hexdigest()==before
    protected=json.loads((OUT/'protected_before.json').read_text())
    assert all(sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in protected.items())
    (OUT/'integrity.json').write_text(json.dumps({'status':'PASS','frozen_sha256':before,'protected_files_unchanged':len(protected)},indent=2)+'\n')


if __name__=='__main__':main()
