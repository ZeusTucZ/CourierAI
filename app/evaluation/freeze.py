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
    policy=StrategyPolicy.model_validate(payload['parameters'])
    if fingerprint(profile,model,policy)!=payload['experiment_sha256']:
        raise ValueError('Frozen experiment fingerprint mismatch')
    return profile,model,policy
