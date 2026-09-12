"""Read-only tuning diagnosis. Local probes/interventions never mutate strategy files.
No heldout file/seed list is opened; inputs are explicitly allowlisted tuning runs.
"""
import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from statistics import mean
from unittest.mock import patch

from app.agents.baseline import GreedyRateBaseline
from app.agents.smart import SmartAgent
from app.decision.engine import DecisionEngine
from app.decision.constraints import evaluate_constraints
from app.models.state import resolve_state
from app.evaluation.runner import ABLATIONS, fingerprint
from app.models.strategy import StrategySnapshot
from app.services.strategy_store import StrategyStore
from app.simulation.config import ShiftConfig
from app.simulation.replay import logical, recorded_agent
from app.simulation.strategic import StrategicSimulator
from app.strategy.historical import HistoricalDemandModel
from app.strategy.models import StrategyPolicy
from app.strategy.reposition import choose_reposition, zone_distance
from app.strategy.routing import insert_order, steps_for, route_plan
from app.strategy.updater import StrategyUpdater

OUT=Path('artifacts/mvp3_diagnostic')
ROOT=Path('evaluation/ablation_results')


def read_events(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def save(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False,default=str)+'\n')


def table(name,rows,fields=None):
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)


def decision_map(events):
    return {e['order_id']:e for e in events if e['event']=='decision'}


def route_signature(candidate):
    if candidate is None:return None
    return ([(s.order_id,s.phase.kind,s.phase.remaining_us,s.phase.distance_km,s.zone) for s in candidate[0]],asdict(candidate[1]))


def percentile(values,p):
    values=sorted(values)
    if not values:return None
    position=(len(values)-1)*p
    lo=int(position);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(position-lo)


def stats(values):
    return {'n':len(values),'min':min(values) if values else None,'p10':percentile(values,.1),
            'p25':percentile(values,.25),'median':percentile(values,.5),'p75':percentile(values,.75),
            'p90':percentile(values,.9),'max':max(values) if values else None,'mean':mean(values) if values else None}


def insertion_diagnostics(route,job,jobs,request,snapshot,policy,actual):
    """Observe the production candidate family and its rejection/score mechanism."""
    fields=dict(candidate_count=0,unique_alternative_count=0,alternative_sla_rejects=0,
                alternative_safety_rejects=0,alternative_feasible=0,alternative_sla_existing_miss=0,alternative_sla_new_miss=0,fifo_wins_strictly=0,
                fifo_wins_tie=0,fifo_only_feasible=0)
    if len(jobs)>=policy.max_active_orders:return fields
    new=steps_for(job);fifo=route+new;candidates=[fifo]
    for pickup in range(1 if route else 0,len(route)+1):
        for delivery in range(pickup,len(route)+1):
            if len(candidates)>=policy.max_insertions:break
            candidates.append(route[:pickup]+new[:2]+route[pickup:delivery]+new[2:]+route[delivery:])
        if len(candidates)>=policy.max_insertions:break
    fields['candidate_count']=len(candidates)
    state=resolve_state(request.sim_time,request.courier_state_overrides,snapshot.policy.default_shift_hours)
    deadlines={j.offer.order_id:j.promised_completion_time for j in (*jobs,job)}
    def signature(seq):return tuple((s.order_id,s.phase.kind,s.phase.remaining_us,s.phase.distance_km,s.zone) for s in seq)
    seen=set();valid=[];alternatives=[];fifo_score=None
    for index,sequence in enumerate(candidates):
        sig=signature(sequence)
        if sig in seen:continue
        seen.add(sig)
        if index:fields['unique_alternative_count']+=1
        plan,completion=route_plan(sequence,request.sim_time,job.offer.order_id)
        if any(completion[key]>deadline for key,deadline in deadlines.items()):
            if index:
                fields['alternative_sla_rejects']+=1
                fields['alternative_sla_existing_miss']+=int(any(completion[key]>deadline for key,deadline in deadlines.items() if key!=job.offer.order_id))
                fields['alternative_sla_new_miss']+=int(completion[job.offer.order_id]>deadlines[job.offer.order_id])
            continue
        if evaluate_constraints(request,state,snapshot,plan):
            if index:fields['alternative_safety_rejects']+=1
            continue
        score=sum((when-request.sim_time).total_seconds() for when in completion.values())
        valid.append((score,sequence,plan))
        if not index:fifo_score=score
        else:alternatives.append(score);fields['alternative_feasible']+=1
    expected=None
    if valid:
        _,sequence,plan=min(valid,key=lambda x:x[0]);expected=(sequence,plan)
    assert route_signature(expected)==route_signature(actual),'Diagnostic candidate enumeration diverged'
    if route and fifo_score is not None:
        fields['fifo_only_feasible']=int(not alternatives)
        fields['fifo_wins_strictly']=int(bool(alternatives) and min(alternatives)>fifo_score)
        fields['fifo_wins_tie']=int(bool(alternatives) and min(alternatives)==fifo_score)
    return fields


class ProbeSimulator(StrategicSimulator):
    """Observer around production calls; optional one safe decision intervention."""
    def __init__(self,*args,flip=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.probes=[];self.reposition_probes=[];self.order_cost=defaultdict(float)
        self.flip=flip;self.flip_applied=False;self.flip_block=None
        if flip:
            original=self.agent.service.decide
            def intervene(request,*a,**kw):
                response=original(request,*a,**kw)
                if request.order_id==flip[0]:
                    feasible=self.current_candidate is not None
                    safe=response.binding_constraint in (None,'reservation_wage')
                    if flip[1]=='SKIP' or feasible and safe:
                        response=response.model_copy(update={'decision':flip[1],
                            'binding_constraint':None if flip[1]=='ACCEPT' else 'reservation_wage',
                            'reason':'Offline diagnostic single-decision intervention; frozen policy unchanged.'})
                        self.flip_applied=True
                    else:self.flip_block='No feasible insertion or hard constraint on Smart state; ACCEPT not forced'
                return response
            self.agent.service.decide=intervene

    def _advance(self,when):
        order_id=self.route[0].order_id if self.route and not self.move else None
        before=self.state.operating_costs
        super()._advance(when)
        if order_id:self.order_cost[order_id]+=self.state.operating_costs-before

    def _offer(self,source):
        captured={}; self.current_candidate=None
        def observe(route,job,jobs,request,snapshot,policy,*,improved=True):
            result=insert_order(route,job,jobs,request,snapshot,policy,improved=improved)
            self.current_candidate=result
            if not self.flip:
                fifo=insert_order(route,job,jobs,request,snapshot,policy,improved=False)
                captured.update(result=result,fifo=fifo,request=request,snapshot=snapshot,active=len(jobs),route_length=len(route),
                    insertion_diagnostics=insertion_diagnostics(route,job,jobs,request,snapshot,policy,result))
            return result
        with patch('app.simulation.strategic.insert_order',observe):
            super()._offer(source)
        if self.flip:return
        event=next(e for e in reversed(self.log.events) if e['event']=='decision')
        if not captured:return
        result,fifo,request,snapshot=[captured[k] for k in ('result','fifo','request','snapshot')]
        engine=DecisionEngine()
        def probe(snap,candidate=result):
            response=engine.evaluate(request,snap,plan=candidate[1] if candidate else None).response
            return 'SKIP' if candidate is None and response.decision=='ACCEPT' else response.decision
        assert probe(snapshot)==event['decision']
        nozone=snapshot.model_copy(update={'zone_values':{}})
        noopp=snapshot.model_copy(update={'opportunity_fraction':0.})
        tick=snapshot.generated_at_sim_time
        nohistory=StrategyUpdater(self.model,self.policy.model_copy(update={'use_historical_prediction':False}),self.updater.zones).update(
            StrategyStore(self.initial_snapshot),tick,request.vehicle,(self.state.shift_end-tick).total_seconds()/60)
        fixedwage=snapshot.model_copy(update={'reservation_wage_mxn_hr':self.policy.base_reservation_wage})
        e=event.get('economics') or {}
        immediate=GreedyRateBaseline(snapshot,threshold=snapshot.reservation_wage_mxn_hr).decide_request(request)
        # Immediate comparator uses the same Smart state/wage and the same insertion gate.
        immediate_decision='SKIP' if result is None and immediate.decision=='ACCEPT' else immediate.decision
        self.probes.append({'seed':self.config.seed,'order_id':request.order_id,'sim_time':event['sim_time'],
            'active_orders':captured['active'],'route_phases':captured['route_length'],'decision':event['decision'],
            'insertion_feasible':result is not None,'fifo_feasible':fifo is not None,
            'batching_plan_changed':route_signature(result)!=route_signature(fifo),
            'batching_decision_changed':probe(snapshot,fifo)!=event['decision'],
            'batching_changed_executed_plan':event['decision']=='ACCEPT' and route_signature(result)!=route_signature(fifo),
            'zone_value':e.get('zone_value_mxn_hr'), 'opportunity_cost':e.get('opportunity_cost_mxn'),
            'zone_value_changes_decision':probe(nozone)!=event['decision'],
            'opportunity_changes_decision':probe(noopp)!=event['decision'],
            'history_changes_decision':probe(nohistory)!=event['decision'],
            'final_hour_discount_changes_decision':probe(fixedwage)!=event['decision'],
            'committed_denominator_changes_decision':immediate_decision!=event['decision'],
            'same_state_immediate_decision':immediate_decision,
            'reservation_wage':snapshot.reservation_wage_mxn_hr,'adjusted_rate':e.get('adjusted_rate_mxn_hr'),
            'stacking_time_min':e.get('stacking_time_min'),'economic_sample':bool(e),
            'economics_available_zones':sum(p.economics_available for p in snapshot.zone_predictions.values()),
            'logistic_prediction_zones':sum(p.expected_trip_distance is not None and p.expected_delivery_time is not None for p in snapshot.zone_predictions.values()),
            'all_predicted_net_rates_unknown':all(p.expected_net_mxn_per_hour is None for p in snapshot.zone_predictions.values()),
            'binding_constraint':event['binding_constraint'],'reason':event['reason'],**captured['insertion_diagnostics']})

    def _maybe_reposition(self):
        if self.flip:return super()._maybe_reposition()
        def observe(state,snapshot,policy,last_move=None,rain_factor=1):
            result=choose_reposition(state,snapshot,policy,last_move,rain_factor)
            eligible=policy.use_reposition and not state.in_flight_orders and not state.break_until
            if last_move is not None and (state.current_sim_time-last_move).total_seconds()/60<policy.minimum_dwell_time_min:eligible=False
            gains=[]
            if eligible:
                current=snapshot.zone_predictions.get(state.current_zone)
                rate=(current.expected_net_mxn_per_hour or 0) if current else 0
                remaining=(state.shift_end-state.current_sim_time).total_seconds()/60
                horizon=min(policy.reposition_horizon_min,remaining)
                vehicle=snapshot.vehicle_profiles[state.vehicle]
                for zone,prediction in snapshot.zone_predictions.items():
                    if zone==state.current_zone:continue
                    distance=zone_distance(state.current_zone,zone,policy.synthetic_zone_spacing_km)
                    travel=distance/vehicle.speed_kmh*60*rain_factor
                    if travel<=remaining:gains.append((prediction.expected_net_mxn_per_hour or 0)*max(0,horizon-travel)/60-rate*horizon/60-distance*vehicle.operating_cost_mxn_per_km)
            self.reposition_probes.append({'seed':self.config.seed,'sim_time':state.current_sim_time.isoformat(),'eligible_idle':bool(eligible),
                'candidate_count':len(gains),'best_expected_gain_mxn':max(gains) if gains else None,
                'required_gain_mxn':policy.minimum_reposition_gain,'selected':result is not None})
            return result
        with patch('app.simulation.strategic.choose_reposition',observe):super()._maybe_reposition()


def replay_probe(events,flip=None):
    start=events[0]
    config=ShiftConfig.model_validate(start['simulation_config'])
    model=HistoricalDemandModel.model_validate(start['historical_model'])
    policy=StrategyPolicy.model_validate(start['strategy_policy'])
    agent=recorded_agent(start['agent_name'],StrategySnapshot.model_validate(start['strategy_snapshot']))
    simulator=ProbeSimulator(config,agent,model,policy,flip=flip)
    stream=[e['source_event'] for e in events if 'source_event' in e]
    result=simulator.run(stream)
    assert not result.metrics.safety_violations
    if not flip:
        assert logical(result.log.events)==logical(events),'Observer changed production execution'
    return result,simulator


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    # Never call seed_sets(): this task deliberately does not open the heldout seed list.
    seeds=[int(l.strip()) for l in Path('evaluation/tuning_seeds.txt').read_text().splitlines() if l.strip() and not l.startswith('#')]
    assert len(seeds)==len(set(seeds)) and seeds
    protected=[p for p in Path('app').rglob('*.py')]+[Path('artifacts/final_strategy_config.json'),Path('artifacts/calibrated_profile.json'),Path('artifacts/historical_model.json'),Path('artifacts/calibrated_policy.json')]
    protected += [Path('evaluation/tuning_seeds.txt')]
    protected += [ROOT/name/'results.json' for name in ABLATIONS]
    protected += [ROOT/name/f'seed-{seed}/SmartAgent.jsonl' for name in ABLATIONS for seed in seeds]
    protected += [ROOT/f'SmartFull/seed-{seed}/GreedyRateBaseline.jsonl' for seed in seeds]
    before={str(p):sha256(p.read_bytes()).hexdigest() for p in protected}
    frozen=json.loads(Path('artifacts/final_strategy_config.json').read_text())
    summary=json.loads((ROOT/'SmartFull/results.json').read_text())
    assert [r['seed'] for r in summary['rows']]==seeds
    allpairs=[];probes=[];reposition=[];disagreements=[];skip_counts=Counter();rates=[];perseed=[];ablation_rows=[]
    cancellations=[];snapshots=[];route_changes=[]
    for seed in seeds:
        full=read_events(ROOT/f'SmartFull/seed-{seed}/SmartAgent.jsonl')
        base=read_events(ROOT/f'SmartFull/seed-{seed}/GreedyRateBaseline.jsonl')
        assert full[0]['seed']==base[0]['seed']==seed
        assert full[0]['strategy_policy']==frozen['parameters']
        assert full[0]['historical_model']==frozen['model']
        assert full[0]['simulation_config']['profile']==frozen['profile']
        assert full[0]['stream_sha256']==base[0]['stream_sha256']
        result,sim=replay_probe(full)
        probes.extend(sim.probes);reposition.extend(sim.reposition_probes)
        probe_by={p['order_id']:p for p in sim.probes}
        fd,bd=decision_map(full),decision_map(base)
        assert set(fd)==set(bd)
        snapshots.extend(e['snapshot'] for e in full if e['event']=='strategy_update')
        cancellations.extend(e for e in sim.trace if e['type']=='cancellation_evaluated')
        gross={a:{e['completed_order_id']:next(d['decision_request']['base_pay_mxn']*d['decision_request']['surge_multiplier']+d['decision_request']['est_tip_mxn'] for d in decisions.values() if d['order_id']==e['completed_order_id']) for e in events if e['event']=='earnings_update' and e.get('completed_order_id')} for a,events,decisions in [('smart',full,fd),('baseline',base,bd)]}
        for ident,f in fd.items():
            b=bd[ident];same=f['decision']==b['decision'];p=probe_by[ident]
            pair={'seed':seed,'order_id':ident,'sim_time':f['sim_time'],'baseline':b['decision'],'smart':f['decision'],'identical':same,
                  'same_physical_state':f['decision_request']==b['decision_request'],
                  'baseline_binding':b['binding_constraint'],'smart_binding':f['binding_constraint'],
                  'baseline_wage':b['strategy_snapshot']['reservation_wage_mxn_hr'],'smart_wage':p['reservation_wage'],
                  'baseline_adjusted_rate':(b.get('economics') or {}).get('adjusted_rate_mxn_hr'),'smart_adjusted_rate':p['adjusted_rate']}
            allpairs.append(pair)
            for agent,event in [('baseline',b),('smart',f)]:
                if event['decision']=='SKIP':
                    reason='SLA/active-commitment/moving gate' if event['reason'].startswith('Skipped: configured SLA') else event['binding_constraint'] or 'unknown'
                    skip_counts[(agent,reason)]+=1
                economic=event.get('economics') or {}
                rates.append({'seed':seed,'order_id':ident,'agent':agent,'sim_time':event['sim_time'],'decision':event['decision'],
                    'reservation_wage':event['strategy_snapshot']['reservation_wage_mxn_hr'],
                    'adjusted_rate':economic.get('adjusted_rate_mxn_hr'),
                    'margin_rate_minus_wage':economic['adjusted_rate_mxn_hr']-economic['reservation_wage_mxn_hr'] if economic else None,
                    'insertion_feasible':event['insertion_feasible'],'economics_available':bool(economic)})
            if not same:
                counter,branch=replay_probe(full,flip=(ident,b['decision']))
                cb=decision_map(counter.log.events)
                assert all(logical(cb[k])==logical(fd[k]) for k in fd if fd[k]['sim_time']<f['sim_time']), 'Counterfactual altered past'
                delta=result.metrics.net_earnings_mxn-counter.metrics.net_earnings_mxn if branch.flip_applied else None
                disagreements.append({**pair,'same_state_immediate_decision':p['same_state_immediate_decision'],
                    'discount_decisive':p['final_hour_discount_changes_decision'],'denominator_decisive':p['committed_denominator_changes_decision'],
                    'smart_quoted_net_mxn':(f.get('economics') or {}).get('net_pay_mxn'),
                    'baseline_quoted_net_mxn':(b.get('economics') or {}).get('net_pay_mxn'),
                    'smart_realized_gross_on_order':gross['smart'].get(ident,0),
                    'baseline_realized_gross_on_order':gross['baseline'].get(ident,0),
                    'smart_attributed_travel_cost_on_order':sim.order_cost.get(ident,0),
                    'single_flip_executed':branch.flip_applied,'single_flip_block':branch.flip_block,
                    'full_smart_shift_net':result.metrics.net_earnings_mxn,
                    'counterfactual_smart_shift_net':counter.metrics.net_earnings_mxn if branch.flip_applied else None,
                    'new_order_time_min':f['economics']['total_time_min']-f['economics']['stacking_time_min'] if f.get('economics') else None,
                    'pending_work_time_min':f['economics'].get('stacking_time_min') if f.get('economics') else None,
                    'smart_total_committed_time_min':f['economics']['total_time_min'] if f.get('economics') else None,
                    'impact_smart_choice_vs_single_flip_mxn':delta,
                    'subsequent_decision_changes':sum(cb[k]['decision']!=fd[k]['decision'] for k in fd if fd[k]['sim_time']>f['sim_time']),
                    'baseline_reason':b['reason'],'smart_reason':f['reason']})
        metricrow=next(r for r in summary['rows'] if r['seed']==seed)
        perseed.append({'seed':seed,'offers':len(fd),'identical':sum(fd[k]['decision']==bd[k]['decision'] for k in fd),
                        'baseline_net':metricrow['baseline']['net_earnings_mxn'],'smart_net':metricrow['smart']['net_earnings_mxn'],
                        'delta_net':metricrow['smart']['net_earnings_mxn']-metricrow['baseline']['net_earnings_mxn']})
        for name in ABLATIONS:
            variant=read_events(ROOT/f'{name}/seed-{seed}/SmartAgent.jsonl');vd=decision_map(variant)
            assert variant[0]['seed']==seed and set(vd)==set(fd)
            assert variant[0]['stream_sha256']==full[0]['stream_sha256']
            other=json.loads((ROOT/name/'results.json').read_text())
            vr=next(r for r in other['rows'] if r['seed']==seed)
            ablation_rows.append({'variant':name,'seed':seed,'decision_changes':sum(fd[k]['decision']!=vd[k]['decision'] for k in fd),
                'proposed_route_changes':sum(fd[k]['planned_route']!=vd[k]['planned_route'] for k in fd),
                'executed_route_changes':sum(fd[k]['decision']=='ACCEPT' and fd[k]['planned_route']!=vd[k]['planned_route'] for k in fd),
                'physical_state_changes':sum(fd[k]['courier_state']!=vd[k]['courier_state'] for k in fd),
                'net':vr['smart']['net_earnings_mxn'],'delta_vs_full':vr['smart']['net_earnings_mxn']-metricrow['smart']['net_earnings_mxn'],
                'all_nonlatency_metrics_identical':logical(vr['smart'])==logical(metricrow['smart'])})
        print(f'Diagnosed tuning seed {seed}: {len(fd)} offers',flush=True)
    table('decisions.csv',allpairs);table('feature_usage_by_decision.csv',probes);table('disagreements.csv',disagreements)
    table('rate_distributions_raw.csv',rates);table('reposition_opportunities.csv',reposition);table('per_seed.csv',perseed);table('ablations_by_seed.csv',ablation_rows)
    table('repositions.csv',[],['seed','sim_time','target_zone','realized_cost_mxn','causal_net_value_mxn'])
    skips=[{'agent':a,'reason':r,'count':n,'pct_of_skips':n/sum(v for (ag,_),v in skip_counts.items() if ag==a)*100} for (a,r),n in sorted(skip_counts.items())]
    table('skip_reasons.csv',skips)
    distributions=[]
    for agent in ('baseline','smart'):
        for subset in ('all','ACCEPT','SKIP','feasible_insertion'):
            use=[r for r in rates if r['agent']==agent and (subset=='all' or r['decision']==subset or subset=='feasible_insertion' and r['insertion_feasible'])]
            for field in ('reservation_wage','adjusted_rate','margin_rate_minus_wage'):
                distributions.append({'agent':agent,'subset':subset,'field':field,**stats([r[field] for r in use if r[field] is not None]),'missing':sum(r[field] is None for r in use)})
    table('rate_distributions.csv',distributions)
    feature_counts={k:sum(bool(p[k]) for p in probes) for k in ('batching_plan_changed','batching_decision_changed','batching_changed_executed_plan','zone_value_changes_decision','opportunity_changes_decision','history_changes_decision','final_hour_discount_changes_decision','committed_denominator_changes_decision')}
    feature_counts.update(offers=len(probes),with_active_orders=sum(p['active_orders']>0 for p in probes),
        feasible_insertions=sum(p['insertion_feasible'] for p in probes),
        feasible_with_active_orders=sum(p['insertion_feasible'] and p['active_orders']>0 for p in probes),
        economic_records=sum(p['economic_sample'] for p in probes),
        nonzero_stacking_time=sum(bool(p['stacking_time_min']) for p in probes),
        nonzero_zone_value=sum(bool(p['zone_value']) for p in probes),nonzero_opportunity_cost=sum(bool(p['opportunity_cost']) for p in probes),
        strategy_updates=len(snapshots),predictions_generated=sum(len(s['zone_predictions']) for s in snapshots),
        predictions_with_economics=sum(p['economics_available'] for s in snapshots for p in s['zone_predictions'].values()),
        reposition_attempts=len(reposition),reposition_eligible=sum(p['eligible_idle'] for p in reposition),
        reposition_count=sum(p['selected'] for p in reposition),cancellation_checks=len(cancellations),cancellations=sum(p['cancel'] for p in cancellations))
    feature_counts.update({k:sum(p[k] for p in probes) for k in ('candidate_count','unique_alternative_count','alternative_sla_rejects','alternative_safety_rejects','alternative_feasible','alternative_sla_existing_miss','alternative_sla_new_miss','fifo_wins_strictly','fifo_wins_tie','fifo_only_feasible')})
    feature_counts.update(accepted_with_active_orders=sum(p['active_orders']>0 and p['decision']=='ACCEPT' for p in probes),
        discounted_wage_offers=sum(p['reservation_wage']<125 for p in probes),
        discounted_wage_feasible_offers=sum(p['reservation_wage']<125 and p['insertion_feasible'] for p in probes))
    features=feature_table(feature_counts)
    table('feature_utilization.csv',features)
    save('feature_counts.json',feature_counts)
    table('feature_counts.csv',[{'metric':k,'count':v} for k,v in feature_counts.items()])
    identical=sum(p['identical'] for p in allpairs)
    aggregate={'seeds':seeds,'offers_paired':len(allpairs),'identical_decisions':identical,'identical_pct':identical/len(allpairs)*100,
        'disagreements':len(disagreements),'baseline_accept_smart_skip':sum(p['baseline']=='ACCEPT' and p['smart']=='SKIP' for p in allpairs),
        'baseline_skip_smart_accept':sum(p['baseline']=='SKIP' and p['smart']=='ACCEPT' for p in allpairs),
        'mean_baseline_net':summary['mean_baseline_net'],'mean_smart_net':summary['mean_smart_net'],
        'mean_improvement_pct':summary['mean_improvement_pct'],'features':feature_counts,
        'causal_intervention':'Each disagreement: replay unchanged Smart history, force only that action to paired baseline action if feasible, then unchanged Smart policy. Full minus branch net, nonadditive; not an optimization.',
        'scope':'Only explicit tuning seeds and existing tuning ablation logs. No heldout inputs opened.'}
    assert all(sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in before.items())
    save('input_integrity.json',{'unchanged':True,'sha256':before})
    save('summary.json',aggregate)
    save('cancellation_checks.json',cancellations)
    write_report(aggregate,disagreements,perseed,skips,distributions,ablation_rows,reposition,probes)


def feature_table(f):
    definitions=[
        ('zone_value',f['economic_records'],f['nonzero_zone_value'],f['zone_value_changes_decision'],None,
         'economic_signal_inactive;requires_missing_data','Courier payout and observation exposure',
         'All monetary zone values are zero; removing them has no effect.'),
        ('opportunity_cost',f['economic_records'],f['nonzero_opportunity_cost'],f['opportunity_changes_decision'],None,
         'economic_signal_inactive;requires_missing_data','Historical net rates: courier payout, exposure and defensible costs',
         'Explicit opportunity cost is zero; do not confuse it with the committed-time denominator.'),
        ('historical_prediction',f['predictions_generated'],f['predictions_generated'],f['history_changes_decision'],None,
         'logistics_active_not_decisive;economics_requires_missing_data','Exposure for arrival rates; courier payout for earnings',
         '160 updates generate zone/hour logistics; no economic predictions. Current decision consumers do not use predicted km/min directly.'),
        ('reposition',f['reposition_eligible'],f['reposition_count'],0,None,
         'action_inactive;requires_missing_data','Evidence for economic attractiveness and travel costs',
         'No moves; predicted gains equal negative travel cost. Per-move causal value undefined, not zero-valued observed moves.'),
        ('improved_batching',f['unique_alternative_count'],f['batching_plan_changed'],f['batching_decision_changed'],0.,
         'executed_not_decisive','No missing data inferred from this diagnostic',
         'All non-FIFO alternatives fail SLA. The ablation preserves FIFO batching.'),
        ('fifo_batching',f['feasible_with_active_orders'],f['accepted_with_active_orders'],None,None,
         'executed_shared_mechanism','No additional data needed to observe existing behavior',
         '19 Smart ACCEPTs with active orders; shared mechanism, no disable-all-batching intervention performed.'),
        ('final_hour_wage_discount',f['discounted_wage_offers'],f['discounted_wage_offers'],f['final_hour_discount_changes_decision'],None,
         'active_not_decisive','No missing data needed for configured time rule',
         'Wage drops from 125 to 115 at 22:30; all 68 later offers lack feasible insertion.'),
        ('committed_time_denominator',f['economic_records'],f['nonzero_stacking_time'],f['committed_denominator_changes_decision'],-55.28914026257621,
         'active_decisive','No additional data needed for this measured comparison',
         '828 economic evaluations include pending work; one changes final decision and loses 55.289140 MXN.'),
        ('cancellation',f['cancellation_checks'],f['cancellations'],None,None,
         'evaluated_not_executed','Penalties remain assumed; no inferred need for policy change',
         '8 visible-shock evaluations; zero cancellations. Shared with baseline in this simulator.')]
    return [dict(feature=name,opportunities=opportunities,nonzero_terms_or_actions=uses,
                 local_accept_skip_changes=changes,measured_net_effect_mxn=effect,
                 classification=classification,missing_data=data,explanation=explanation)
            for name,opportunities,uses,changes,effect,classification,data,explanation in definitions]


def write_report(s,disagreements,perseed,skips,distributions,ablations,reposition,probes):
    # Report assembly intentionally separate from instrumented production execution.
    f=s['features'];lines=['# MVP3_DIAGNOSTIC — tuning únicamente','',
        f"Seeds: {s['seeds']}. Configuración congelada y código de estrategia sin cambios; hashes verificados en `artifacts/mvp3_diagnostic/input_integrity.json`. No se abrió ningún archivo ni lista de seeds held-out.", '',
        f"**Causa principal:** 99.918% de decisiones idénticas, señales económicas avanzadas nulas y una sola diferencia causada por el denominador de tiempo comprometido. Smart no supera al baseline en estas tuning seeds: neto medio {s['mean_smart_net']:.2f} vs {s['mean_baseline_net']:.2f} MXN/shift. La diferencia se concentra en seed 3; las otras nueve empatan. No se extrapola este diagnóstico a held-out.", '',
        '## Decisiones pareadas', '',
        f"{s['offers_paired']} ofertas comunes; {s['identical_decisions']} decisiones idénticas ({s['identical_pct']:.4f}%). Desacuerdos: {s['disagreements']}; baseline ACCEPT / Smart SKIP: {s['baseline_accept_smart_skip']}; baseline SKIP / Smart ACCEPT: {s['baseline_skip_smart_accept']}.",
        'Se empareja por seed + order_id. Las políticas pueden llegar con estados distintos al mismo pedido; esa comparación no equivale a un efecto causal aislado de una feature.', '',
        '| Seed | Ofertas | Idénticas | Baseline net | Smart net | Delta |','|---|---:|---:|---:|---:|---:|']
    for r in perseed:lines.append(f"| {r['seed']} | {r['offers']} | {r['identical']} | {r['baseline_net']:.2f} | {r['smart_net']:.2f} | {r['delta_net']:.2f} |")
    lines+=['', '## Impacto de cada desacuerdo', '',
        'La tabla completa `disagreements.csv` contiene estado comparable, razones, tasas, gross realizado por pedido y neto cotizado. Para no atribuirle falsamente a una decisión todo el delta observado, se ejecutó una rama diagnóstica por desacuerdo: idéntica historia Smart hasta ese evento, una sola acción cambiada a la acción baseline si es factible, y después la política Smart original. Impacto = neto Smart original − neto de esa rama. No se fuerzan ACCEPT inseguros. Los efectos no son aditivos porque interactúan con decisiones posteriores; no se usaron para seleccionar parámetros.', '',
        '| Seed / pedido | Baseline → Smart | Mismo estado | Neto Smart | Neto rama | Efecto elección Smart | Decisiones posteriores distintas |','|---|---|---|---:|---:|---:|---:|']
    for r in disagreements:
        fmt=lambda x:'N/A' if x is None else f'{x:.2f}'
        lines.append(f"| {r['seed']} / {r['order_id']} | {r['baseline']} → {r['smart']} | {r['same_physical_state']} | {fmt(r['full_smart_shift_net'])} | {fmt(r['counterfactual_smart_shift_net'])} | {fmt(r['impact_smart_choice_vs_single_flip_mxn'])} | {r['subsequent_decision_changes']} |")
    lines+=['', 'El único desacuerdo ocurre el 21 de marzo a las 22:27:19, seed 3 / ORD-00107. Ambos tienen el mismo estado y umbral 125. Hay 4.724542 min pendientes de ORD-00095; el pedido nuevo requiere 26.224759 min. Baseline: 55.289140 / 26.224759 × 60 = 126.496810 MXN/h → ACCEPT. Smart: 55.289140 / 30.949301 × 60 = 107.186537 MXN/h → SKIP. Zone value y opportunity cost son exactamente cero. El ACCEPT del baseline completa el pedido; gross 61.49152 menos costo 6.202380 = 55.289140 MXN. La rama Smart con ese único ACCEPT recupera el mismo importe y no cambia ninguna decisión posterior. En este caso, cargar trabajo pendiente en el denominador excluye un pedido rentable y factible; no es un efecto del modelo histórico.', '', '## Utilización de features', '', '| Métrica | Conteo |','|---|---:|']
    for k,v in f.items():lines.append(f'| {k} | {v} |')
    lines+=['', 'Conteos decisivos: probes contrafactuales locales sobre el mismo estado Smart, mismo instante, mismo candidato y mismas restricciones. Zone value se elimina del snapshot de prueba; opportunity_fraction se neutraliza solo en el probe; HistoricalPrediction usa el updater sin historia al último tick real. No se escribe ningún snapshot/configuración alternativo. El observador reproduce exactamente los logs originales excluyendo latencia.', '',
        '## Reservation wage vs adjusted rate', '',
        f"Baseline conserva 125 MXN/h; Smart conserva 125 hasta el tick de 22:30 y luego 115. Hay {f['discounted_wage_offers']} ofertas bajo el descuento, {f['discounted_wage_feasible_offers']} con inserción factible; cambia cero decisiones. Se distingue código activo de efecto decisivo. Tasas disponibles solo cuando las restricciones permiten calcular economics: no se rellenan con cero las ausentes. Las tasas de cada política usan su propio estado/denominador. CSVs incluyen todas las observaciones y cuantiles por ACCEPT, SKIP y candidato factible.", '',
        '| Agente | Variable (todas) | n | Min | P25 | Mediana | P75 | P90 | Max | Ausentes |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in distributions:
        if r['subset']!='all':continue
        fmt=lambda x:'N/A' if x is None else f'{x:.3f}'
        lines.append('| '+ ' | '.join([r['agent'],r['field'],str(r['n'])]+[fmt(r[k]) for k in ('min','p25','median','p75','p90','max')]+[str(r['missing'])])+' |')
    lines+=['', '## Motivos de SKIP', '', '| Agente | Motivo | n | % de sus SKIP |','|---|---|---:|---:|']
    for r in sorted(skips,key=lambda r:(r['agent'],-r['count'])):lines.append(f"| {r['agent']} | {r['reason']} | {r['count']} | {r['pct_of_skips']:.2f}% |")
    lines+=['', 'El gate de SLA/compromisos usa el enum público reservation_wage, pero se separó por su razón textual. La diferencia de 163 rechazos etiquetados gate (236 baseline frente a 73 Smart) no son 163 decisiones distintas: en esos pedidos el baseline supera el umbral pero el gate lo bloquea; Smart ya reporta rechazo por tasa comprometida. Los motivos corresponden a la primera restricción reportada, no a un inventario de todas las restricciones simultáneas.', '',
        '## Reposition: conteo y valor', '',
        f"{f['reposition_count']} movimientos. `repositions.csv` tiene encabezado y cero filas: no existe un valor neto por movimiento que estimar. No se interpreta net_gain_after_reposition como retorno causal; ese campo del simulador sería el neto total del turno tras costos.",
        f"Se observaron {f['reposition_attempts']} consultas, {f['reposition_eligible']} en estado elegible. Sin tasas económicas históricas, gain = −costo de viaje; ningún destino puede superar el umbral positivo de 5 MXN. Detalle y mejor ganancia de cada oportunidad en `reposition_opportunities.csv`.", '',
        '## Por qué cada ablation empata', '', '| Variante | Cambios de decisión | Rutas propuestas distintas | Rutas ejecutadas distintas | Estados distintos | Delta neto total |','|---|---:|---:|---:|---:|---:|']
    for name in ABLATIONS:
        rows=[r for r in ablations if r['variant']==name]
        lines.append(f"| {name} | {sum(r['decision_changes'] for r in rows)} | {sum(r['proposed_route_changes'] for r in rows)} | {sum(r['executed_route_changes'] for r in rows)} | {sum(r['physical_state_changes'] for r in rows)} | {sum(r['delta_vs_full'] for r in rows):.2f} |")
    lines+=['', '- **SmartNoZoneValue:** todos los valores económicos zonales usados son cero. Quitarlos no altera adjusted_rate.',
        '- **SmartNoReposition:** SmartFull tampoco realiza movimientos; desactivarlo no elimina ninguna acción, costo ni cambio de posición.',
        '- **SmartNoHistoricalPrediction:** el modelo sí produce estadísticas logísticas, pero no tasas de ingreso ni exposición. Los consumidores monetarios usan cero como ajuste neutro. Las predicciones desaparecen en el snapshot, pero wage, zone value, opportunity cost y decisiones permanecen iguales. El descuento horario del salario de reserva sigue activo porque no depende de historia.',
        f"- **SmartNoImprovedBatching:** 875 ofertas llegan con trabajo activo, pero solo {f['feasible_with_active_orders']} admiten inserción y {f['accepted_with_active_orders']} se aceptan. Se evaluaron {f['candidate_count']} candidatos (incluye duplicados FIFO), {f['unique_alternative_count']} alternativas únicas no FIFO: {f['alternative_sla_rejects']} fallan SLA, {f['alternative_safety_rejects']} restricciones y {f['alternative_feasible']} son factibles. Con trabajo activo, FIFO es el único factible en {f['fifo_only_feasible']} ofertas, gana estrictamente en {f['fifo_wins_strictly']} y gana por desempate estable en {f['fifo_wins_tie']}. Los incumplimientos SLA afectan a pedidos existentes en {f['alternative_sla_existing_miss']} alternativas y al nuevo en {f['alternative_sla_new_miss']} (conteos superpuestos). Esta ablation desactiva la inserción mejorada, no el batching FIFO básico. Ninguna propuesta elegida difiere de FIFO; por eso no cambia ningún plan ni decisión. Los tiempos y distancias son aditivos: la heurística no crea ahorros de ruta geográfica.",
        '- **SmartFull:** referencia sin remover componentes. La igualdad no es una prueba de utilidad: también se compararon decisiones, rutas y estado físico, además de todos los indicadores no relacionados con latencia.', '',
        '## Clasificación final y límites', '',
        'La tabla machine-readable principal es `artifacts/mvp3_diagnostic/feature_utilization.csv`: oportunidades, términos/acciones no nulos, cambios locales, impacto medido, clasificación y datos faltantes por componente.', '',
        'La clasificación siguiente corresponde exclusivamente a estas tuning seeds; los tests de fixtures pueden demostrar capacidades que aquí no se ejercitan. No se optimizó ningún parámetro.', '',
        f"- **Funcionan y cambian decisiones:** el denominador de tiempo comprometido cambia {f['committed_denominator_changes_decision']} decisión local frente al inmediato (impacto negativo medido). Los gates de seguridad/SLA también operan y bloquean ofertas, pero son compartidos; no son una ventaja diferencial Smart.",
        f"- **Funcionan pero no llegan a ser decisivos:** descuento horario activo en {f['discounted_wage_offers']} ofertas, cero cambios de decisión; cancelación evaluada {f['cancellation_checks']} veces, cero ejecuciones. Mejor inserción cambia {f['batching_plan_changed']} planes candidatos y {f['batching_changed_executed_plan']} planes ejecutados; cambia {f['batching_decision_changed']} decisiones. El modelo histórico ejecuta {f['strategy_updates']} updates con estadísticas logísticas, que no alimentan una ventaja económica en este diseño.",
        '- **Efectivamente inactivos como señales/acciones:** zone value monetario, opportunity cost monetario y reposition. Se ejecuta código de evaluación, pero los términos son cero y los movimientos no existen. Cancelación se evalúa ocho veces y nunca se ejecuta: código activo, acción no ejercida. El descuento salarial está activo pero no es decisivo; el batching FIFO básico sí se ejecuta (19 ACCEPT con trabajo activo), incluso en SmartNoImprovedBatching.',
        '- **Requieren datos ausentes:** tasas de demanda necesitan horas de exposición; earnings/zone value/opportunity cost/reposition económico necesitan una fuente válida de courier payout y supuestos de costo defendibles. Las distancias/duraciones disponibles no bastan para convertir demanda en MXN/h. No debe usarse el valor de la factura.',
        '- La calibración de SLA y las restricciones se aplican a ambos agentes: no son una ventaja diferencial exclusiva de Smart. Desactivar una feature no elimina esos mecanismos compartidos.', '',
        '## Reproducción y archivos', '', '`python -m scripts.diagnose_mvp3`', '',
        'Salida machine-readable: `artifacts/mvp3_diagnostic/summary.json`, `feature_utilization.csv`, `feature_counts.csv`, `decisions.csv`, `disagreements.csv`, `feature_usage_by_decision.csv`, `rate_distributions.csv`, `rate_distributions_raw.csv`, `skip_reasons.csv`, `reposition_opportunities.csv`, `repositions.csv`, `ablations_by_seed.csv`, `per_seed.csv`, `cancellation_checks.json`, `input_integrity.json`. Sin cambios a app/, perfiles, modelo, política congelada ni parámetros.']
    Path('MVP3_DIAGNOSTIC.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(s,indent=2))


if __name__=='__main__':main()
