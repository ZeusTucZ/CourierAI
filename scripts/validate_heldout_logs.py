"""Validate and replay every heldout agent log without refitting."""
import json
from pathlib import Path
from app.simulation.replay import replay_shift
from validate_format import check_event_log


def main():
    records=[]
    for path in sorted(Path('evaluation/heldout_results').glob('seed-*/*.jsonl')):
        if path.name=='source.jsonl' or '.trace.' in path.name: continue
        errors,counts=check_event_log(str(path))
        if errors: raise RuntimeError(errors)
        result=replay_shift(path)
        records.append({'path':str(path),'decisions_checked':result.decisions_checked,
                        'source_sha256':result.stream_sha256,'events':counts,'status':'PASS'})
    if len(records)<20: raise ValueError('At least 20 heldout agent logs required')
    Path('artifacts/replay_validation.json').write_text(json.dumps(records,indent=2)+'\n')
    print(f'PASS: all {len(records)} heldout agent logs validated and deterministically replayed')


if __name__=='__main__': main()
