"""Content-addressed frozen experiment. Heldout consumes this exact payload."""
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from app.calibration.profiles import SimulationProfile
from app.evaluation.runner import fingerprint
from app.strategy.historical import HistoricalDemandModel
from app.strategy.models import StrategyPolicy


def freeze(path, profile, model, policy):
    payload = {'strategy_version':'public-mvp3-v1','parameters':policy.model_dump(mode='json'),
               'profile_version':profile.name,'profile':profile.model_dump(mode='json'),
               'model':model.model_dump(mode='json'),'timestamp':datetime.now(timezone.utc).isoformat(),
               'experiment_sha256':fingerprint(profile,model,policy)}
    payload['hash'] = sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    path.write_text(json.dumps(payload,indent=2)+'\n')
    return payload


def load_frozen(path):
    payload=json.loads(Path(path).read_text()); expected=payload.pop('hash')
    if sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()!=expected:
        raise ValueError('Frozen configuration hash mismatch')
    profile=SimulationProfile.model_validate(payload['profile'])
    model=HistoricalDemandModel.model_validate(payload['model'])
    # Verify the exact serialized parameters that were originally frozen. New
    # optional policy fields must not invalidate or silently promote an older
    # held-out artifact merely because model validation supplies new defaults.
    original = payload['parameters']
    frozen_fingerprint = sha256(json.dumps([
        profile.model_dump(mode='json'), model.model_dump(mode='json'), original
    ], sort_keys=True).encode()).hexdigest()
    if frozen_fingerprint!=payload['experiment_sha256']:
        raise ValueError('Frozen experiment fingerprint mismatch')
    policy=StrategyPolicy.model_validate({
        **original,
        # Historical artifacts remain on Current Smart until explicitly frozen
        # with a Smart-v2 choice after diagnostic review.
        'use_smart_v2_scoring': original.get('use_smart_v2_scoring', False),
    })
    return profile,model,policy
