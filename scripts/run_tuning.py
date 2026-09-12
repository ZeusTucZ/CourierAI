"""Predeclared bounded search using ONLY tuning seeds; freeze before heldout."""
import json
from pathlib import Path
from app.evaluation.runner import evaluate
from app.evaluation.freeze import freeze
from scripts.mvp3_common import arguments


def main():
    args,profile,model,policy,tuning,_=arguments('Public MVP3 tuning seeds only')
    output=args.output_dir or Path('evaluation/tuning_results')
    # Only the assumed base reservation wage is eligible; safety/SLA are never tuned.
    candidates=(125.,165.,205.)
    outcomes=[]
    for wage in candidates:
        candidate=policy.model_copy(update={'base_reservation_wage':wage})
        result=evaluate(tuning,profile,model,candidate,output=output/f'wage-{wage:g}',vehicle=args.vehicle,hours=args.shift_hours)
        outcomes.append({'base_reservation_wage':wage,'mean_smart_net':result['mean_smart_net'],
                         'mean_baseline_net':result['mean_baseline_net'],'safety_violations':result['safety_violations']})
    best=max(outcomes,key=lambda r:(r['mean_smart_net'],-r['base_reservation_wage']))
    selected=policy.model_copy(update={'base_reservation_wage':best['base_reservation_wage']})
    freeze(Path('artifacts/final_strategy_config.json'),profile,model,selected)
    Path('artifacts/tuning_report.json').write_text(json.dumps({'seeds':tuning,'allowed_parameters':{'base_reservation_wage':candidates},
        'objective':'maximum mean Smart net, lower wage wins ties; no heldout access','outcomes':outcomes,'selected':best},indent=2)+'\n')
    print(json.dumps(outcomes,indent=2));print('Frozen artifacts/final_strategy_config.json')


if __name__=='__main__': main()
