"""Reproducible public-data audit, conservative normalization and offline calibration.
Raw files are immutable. No customer amounts enter courier economics.
"""
import csv
import json
import math
import shutil
import subprocess
import urllib.request
import zipfile
from collections import Counter
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd

from app.calibration.fitting import calibrate
from app.calibration.loaders import NormalizedDeliveryRecord
from app.calibration.profiles import Provenance
from app.strategy.historical import HistoricalDemandModel
from app.strategy.models import StrategyPolicy, SLABucket

OUT = Path('artifacts')
PROCESSED = Path('data/processed')
SOURCES = {'zomato': 'saurabhbadole/zomato-delivery-operations-analytics-dataset',
           'order_history': 'sujalsuthar/food-delivery-order-history-data'}


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False, default=str)+'\n')


def acquire():
    result = {}
    for name, slug in SOURCES.items():
        folder = Path('data/raw') / name
        folder.mkdir(parents=True, exist_ok=True)
        archive = folder / 'dataset.zip'
        try:
            if not archive.exists():
                if shutil.which('kaggle'):
                    subprocess.run(['kaggle', 'datasets', 'download', '-d', slug, '-p', str(folder)], check=True)
                    archive = next(folder.glob('*.zip'))
                else:
                    urllib.request.urlretrieve('https://www.kaggle.com/api/v1/datasets/download/'+slug, archive)
            with zipfile.ZipFile(archive) as z:
                if z.testzip():
                    raise ValueError('ZIP CRC failure')
                for member in z.infolist():
                    target = folder / member.filename
                    if not target.resolve().is_relative_to(folder.resolve()):
                        raise ValueError('Unsafe archive path')
                    if not target.exists():
                        z.extract(member, folder)
                    elif not member.is_dir() and sha256(target.read_bytes()).digest() != sha256(z.read(member)).digest():
                        raise ValueError('Existing raw file differs from archive; preserved unchanged')
            result[name] = {'status': 'available_zip_verified', 'source': 'https://www.kaggle.com/datasets/'+slug,
                            'note': 'Existing archives reused when present; download date/origin of preexisting bytes not independently attested',
                            'archive_sha256': sha256(archive.read_bytes()).hexdigest()}
        except Exception as exc:
            result[name] = {'status': 'download_blocked', 'error': str(exc),
                            'manual_action': 'Configure Kaggle API credentials in ~/.kaggle/kaggle.json (chmod 600), then kaggle datasets download -d '+slug+' -p '+str(folder)+' --unzip. No credentials are read or printed by this script.'}
    root = Path('data/raw/solomon/ML4VRP2026')
    if not root.exists():
        subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/ML4VRP/ML4VRP2026.git', str(root)], check=True)
    result['solomon'] = {'source': 'https://github.com/ML4VRP/ML4VRP2026', 'commit': subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'], text=True).strip()}
    save('data_sources.json', result)
    return result


def audit_frame(frame):
    columns = {}
    for c in frame:
        s = frame[c]
        numeric = pd.to_numeric(s, errors='coerce').dropna()
        entry = {'dtype': str(s.dtype), 'missing': int(s.isna().sum()), 'unique': int(s.nunique()),
                 'numeric_count': len(numeric)}
        if len(numeric):
            q1, q3 = numeric.quantile([.25,.75]); iqr = q3-q1
            entry.update(min=float(numeric.min()), max=float(numeric.max()),
                         negative_count=int((numeric<0).sum()),
                         iqr_outliers=int(((numeric<q1-1.5*iqr)|(numeric>q3+1.5*iqr)).sum()))
        columns[c] = entry
    return {'rows': len(frame), 'duplicates': int(frame.duplicated().sum()), 'columns': columns}


def numeric(frame, c):
    return pd.to_numeric(frame[c], errors='coerce')


def coordinates(frame):
    cols = ['Restaurant_latitude','Restaurant_longitude','Delivery_location_latitude','Delivery_location_longitude']
    a,b,c,d = [numeric(frame,k) for k in cols]
    legal = a.between(-90,90)&c.between(-90,90)&b.between(-180,180)&d.between(-180,180)
    # Dataset-specific plausibility envelope; does not relocate or repair coordinates.
    plausible = legal&a.between(6,38)&c.between(6,38)&b.between(68,98)&d.between(68,98)
    ar,br,cr,dr = [np.radians(x) for x in (a,b,c,d)]
    hav = np.sin((cr-ar)/2)**2 + np.cos(ar)*np.cos(cr)*np.sin((dr-br)/2)**2
    distance = 6371.0088 * 2*np.arcsin(np.sqrt(hav.clip(0,1)))
    return plausible & distance.between(.01,100), distance, {'illegal_or_missing_coordinate_rows':int((~legal).sum()),
        'outside_india_plausibility_envelope':int((legal&~plausible).sum()),
        'distance_zero_or_over_100km':int((plausible&~distance.between(.01,100)).sum())}


def clock_minutes(series):
    """HH:MM or Excel fractional day; 1 means next midnight, never an hour."""
    parsed = pd.to_datetime(series, format='%H:%M', errors='coerce')
    minutes = parsed.dt.hour * 60 + parsed.dt.minute
    fractions = pd.to_numeric(series, errors='coerce')
    return minutes.fillna((fractions * 1440).round().where(fractions.between(0,1)))


def main():
    OUT.mkdir(exist_ok=True); PROCESSED.mkdir(parents=True, exist_ok=True)
    sources = acquire(); frames = {}; audits = {}; cleaning = []; mappings = []
    inventory = {name:[str(p) for p in sorted((Path('data/raw')/name).rglob('*')) if p.is_file() and '.git' not in p.parts] for name in (*SOURCES,'solomon')}
    raw_hashes = {str(p):sha256(p.read_bytes()).hexdigest() for name in SOURCES for p in (Path('data/raw')/name).glob('*.csv')}
    for name in SOURCES:
        paths = sorted((Path('data/raw')/name).glob('*.csv'))
        if not paths: continue
        frame = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
        frames[name] = frame; audits[name] = audit_frame(frame)
        if name == 'zomato':
            _,_,issues = coordinates(frame); audits[name]['impossible_or_anomalous'] = issues
            audits[name]['impossible_or_anomalous']['nonpositive_delivery_duration'] = int((numeric(frame,'Time_taken (min)')<=0).sum())
        else:
            audits[name]['impossible_or_anomalous'] = {c:int((numeric(frame,c)<0).sum()) for c in ('KPT duration (minutes)','Rider wait time (minutes)')}
    # Audit is durably written BEFORE any cleaning.
    save('data_audit_report.json', {'files':inventory,'raw_sha256':raw_hashes,'datasets':audits})
    normalized = {}; contexts = {}; split = {}
    for name, raw in frames.items():
        frame = raw.drop_duplicates().copy()
        cleaning.append({'dataset':name,'transformation':'remove exact duplicate rows','reason':'avoid repeated observations',
                         'rows_affected':len(raw)-len(frame),'before':len(raw),'after':len(frame)})
        if name == 'zomato':
            minutes = clock_minutes(frame.Time_Orderd)
            stamp = pd.to_datetime(frame.Order_Date,format='%d-%m-%Y',errors='coerce') + pd.to_timedelta(minutes,unit='m')
            fractions = pd.to_numeric(frame.Time_Orderd,errors='coerce').between(0,1)
            cleaning.append({'dataset':name,'transformation':'Excel fractional day -> rounded minute; 1 rolls to next midnight', 'reason':'mixed source clock formats', 'rows_affected':int(fractions.sum()),'before':'fractional day strings','after':'local datetime; missing stays null'})
        else:
            stamp = pd.to_datetime(frame['Order Placed At'], format='%I:%M %p, %B %d %Y', errors='coerce')
        dates = sorted(stamp.dropna().dt.normalize().unique())
        cutoff = pd.Timestamp(dates[max(0,int(len(dates)*.8)-1)]) + pd.Timedelta(days=1)-pd.Timedelta(microseconds=1)
        train = stamp.notna() & (stamp<=cutoff)
        split[name] = {'cutoff':cutoff.isoformat(),'training_rows':int(train.sum()),'heldout_rows':int((stamp>cutoff).sum()),'unknown_timestamp_excluded':int(stamp.isna().sum())}
        cleaning.append({'dataset':name,'transformation':'parse timestamps; unknown dates excluded from fitting','reason':'temporal separation',
                         'rows_affected':int(stamp.isna().sum()),'before':len(frame),'after':int(stamp.notna().sum())})
        data = pd.DataFrame(index=frame.index)
        data['timestamp'] = stamp
        mapping = {}
        if name == 'zomato':
            valid, distance, issues = coordinates(frame)
            data['distance_km'] = distance.where(valid)
            data['service_time_min'] = numeric(frame,'Time_taken (min)').where(lambda s:s>0)
            # Order-to-pickup is not measured kitchen preparation; retain only as context.
            pickup = clock_minutes(frame.Time_Order_picked)
            ordered = clock_minutes(frame.Time_Orderd)
            lag = (pickup-ordered)%1440
            frame['order_to_pickup_min'] = lag.where(lag<=180)
            lat = numeric(frame,'Restaurant_latitude'); lon = numeric(frame,'Restaurant_longitude')
            edges_a = np.quantile(lat[train&valid],[1/3,2/3]).tolist()
            edges_b = np.quantile(lon[train&valid],[.25,.5,.75]).tolist()
            for field,a,b in [('pickup_zone',lat,lon),('dropoff_zone',numeric(frame,'Delivery_location_latitude'),numeric(frame,'Delivery_location_longitude'))]:
                data[field] = pd.Series(np.searchsorted(edges_a,a)*4+np.searchsorted(edges_b,b)+1,index=frame.index).where(valid)
            save('abstract_zones.json', {'names':{i:f'zone_{i}' for i in range(1,13)},'latitude_edges':edges_a,'longitude_edges':edges_b,
                'fit':'training pickups only; 3 latitude x 4 longitude quantile bins', 'limitations':'Abstract India structure only; simulator grid distances remain assumed, bins are not cities or road adjacency'})
            cleaning.append({'dataset':name,'transformation':'invalid/anomalous coordinates and distances -> null; no coordinate repair',
                             'reason':'geographic plausibility, zero placeholders, 100km operational threshold','rows_affected':int((~valid).sum()),'before':len(frame),'after':int(valid.sum()),'issues':issues})
            mapping = {'timestamp':('Order_Date + Time_Orderd','derived','DD-MM-YYYY + HH:MM or Excel fractional day; no timezone claimed'),
                       'distance_km':('Restaurant/Delivery latitude/longitude','derived','haversine; straight-line lower bound, not road distance'),
                       'pickup_zone':('Restaurant_latitude/longitude','derived','training quantile grid'),
                       'dropoff_zone':('Delivery_location_latitude/longitude','derived','same training grid'),
                       'service_time_min':('Time_taken (min)','direct','reported delivery duration; start semantics uncertain')}
        else:
            data['distance_km'] = pd.to_numeric(frame.Distance.astype(str).str.extract(r'^\s*(\d+(?:\.\d+)?)\s*km\s*$',expand=False), errors='coerce')
            data['prep_time_min'] = numeric(frame,'KPT duration (minutes)').where(lambda s:s>=0)
            # Preserve delivery logistics only for delivered orders; cancellations retained in context.
            delivered = frame['Order Status'].astype(str).str.lower().eq('delivered')
            for col in ('distance_km','prep_time_min'): data[col] = data[col].where(delivered)
            cleaning.append({'dataset':name,'transformation':'non-delivered duration/distance excluded from successful-delivery fit',
                             'reason':'avoid mixing cancelled and completed services','rows_affected':int((~delivered).sum()),'before':len(frame),'after':int(delivered.sum())})
            mapping = {'timestamp':('Order Placed At','derived','strict local timestamp'),
                       'distance_km':('Distance','derived','parse km suffix, delivered only'),
                       'prep_time_min':('KPT duration (minutes)','direct','nonnegative delivered KPT duration')}
        for field in NormalizedDeliveryRecord.model_fields:
            col,status,transformation = mapping.get(field,('', 'missing','not measured; remains null'))
            mappings.append({'normalized_field':field,'dataset':name,'source_column':col,'transformation':transformation,'status':status,
                             'notes':'Customer bills, restaurant compensation and discounts are never courier payout' if field in ('base_pay_mxn','tip_mxn') else ''})
        for field in data:
            missing = int(data[field].isna().sum())
            cleaning.append({'dataset':name,'transformation':f'normalize {field}',
                'reason':mapping.get(field, ('','','documented adapter'))[2],
                'rows_affected':len(data), 'before':{'rows':len(data),'source_columns':mapping.get(field,('',))[0]},
                'after':{'nonmissing':len(data)-missing,'null':missing}})
        def records(mask):
            return tuple(NormalizedDeliveryRecord.model_validate({k:(v.to_pydatetime() if isinstance(v,pd.Timestamp) else int(v) if k.endswith('_zone') else v)
                        for k,v in row.items() if pd.notna(v)}) for row in data[mask].to_dict('records'))
        normalized[name] = records(train)
        for label,mask in [('train',train),('heldout',stamp>cutoff)]:
            rows = records(mask)
            (PROCESSED/f'{name}_{label}.jsonl').write_text(''.join(r.model_dump_json()+'\n' for r in rows))
        contexts[name] = frame.loc[train].copy()
        # Keep a logistics-only sidecar; do not export customer identifiers or billing.
        fields = ['Type_of_vehicle','multiple_deliveries','Road_traffic_density','Weather_conditions','order_to_pickup_min'] if name=='zomato' else ['Order Status','Rider wait time (minutes)']
        for field in fields:
            mappings.append({'normalized_field':'context.'+field,'dataset':name,'source_column':field,'transformation':'retained as logistics context; not mapped to pay or kitchen prep','status':'derived' if field=='order_to_pickup_min' else 'direct','notes':'sidecar only'})
        frame.loc[train,fields].to_csv(PROCESSED/f'{name}_context.csv',index=False)
        audits[name]['usable_training_records'] = len(normalized[name])
    # Solomon remains a distinct unitless routing product, never merged with food history.
    root = Path('data/raw/solomon/ML4VRP2026/Instances/cvrptw/txt')
    routing = []
    for family in ('C1','C2','R1','R2','RC1','RC2'):
        candidates = sorted(p for p in root.glob(family+'*.txt') if '_' not in p.stem)
        if not candidates: continue
        p = candidates[0]; lines = p.read_text().split('CUSTOMER',1)[1].splitlines(); rows=[]
        for line in lines:
            fields=line.split()
            if len(fields)!=7: continue
            try: rows.append(list(map(float,fields)))
            except ValueError: continue
        frame = pd.DataFrame(rows,columns=['id','x','y','demand','ready','due','service'])
        audit = audit_frame(frame); audit['invalid_windows']=int((frame.ready>frame.due).sum())
        audits[p.stem]=audit
        customers=frame[frame.id!=0]
        nearest=[]
        xy=customers[['x','y']].to_numpy()
        for i, point in enumerate(xy): nearest.append(float(np.min(np.linalg.norm(np.delete(xy,i,axis=0)-point,axis=1))))
        capacity = [l.split() for l in p.read_text().split('CUSTOMER')[0].splitlines() if len(l.split())==2 and all(v.isdigit() for v in l.split())][0]
        routing.append({'instance':p.stem,'family':family,'customers':len(customers),'capacity':int(capacity[1]),
                        'demand_sum':float(customers.demand.sum()),'window_width_mean':float((customers.due-customers.ready).mean()),
                        'nearest_neighbor_mean':float(np.mean(nearest)),'units':'benchmark coordinate/time/demand units; no kg, minutes, geography or pay conversion'})
        customers.to_csv(PROCESSED/f'solomon_{p.stem}.csv',index=False)
    for field in NormalizedDeliveryRecord.model_fields:
        mappings.append({'normalized_field':field,'dataset':'solomon','source_column':'','transformation':'preserved separately in routing units',
                         'status':'not applicable','notes':'No conversion to food delivery time, weight, distance or economics'})
    save('solomon_routing_profile.json', routing)
    with (OUT/'field_mapping.csv').open('w',newline='') as h:
        writer=csv.DictWriter(h,fieldnames=list(mappings[0]));writer.writeheader();writer.writerows(mappings)
    save('data_split_manifest.json',split)
    save('data_cleaning_report.json',cleaning)
    save('data_audit_report.json',{'files':inventory,'raw_sha256':raw_hashes,'datasets':audits})
    if not normalized: raise RuntimeError('No food data available; routing audit completed')
    # Zomato distance/service structure; history contributes measured KPT, avoiding mixed distance definitions.
    rows=list(normalized.get('zomato',()))
    rows += [NormalizedDeliveryRecord(prep_time_min=r.prep_time_min) for r in normalized.get('order_history',()) if r.prep_time_min is not None]
    if not rows: rows=list(normalized['order_history'])
    digest=sha256(''.join(r.model_dump_json() for r in rows).encode()).hexdigest()
    profile,report=calibrate(rows,source='public training partitions; see field_mapping.csv',source_sha256=digest)
    if 'zomato' in contexts:
        context=contexts['zomato']; vehicles=Counter(context.Type_of_vehicle.dropna().astype(str).str.strip())
        multiples=pd.to_numeric(context.multiple_deliveries,errors='coerce').dropna()
        profile=profile.model_copy(update={'vehicle_distribution':tuple(sorted(vehicles.items())),
            'multiple_delivery_frequency':float((multiples>0).mean()) if len(multiples) else None})
    provenance=[]
    for p in profile.provenance:
        if p.parameter in ('order_distance_distribution','zone_transition_distribution') and p.sample_size:
            p=p.model_copy(update={'classification':'derived','transformation':'Training-only haversine km or quantile zone counts; see mapping'})
        provenance.append(p)
    profile=profile.model_copy(update={'provenance':tuple(provenance)})
    profile.save(OUT/'calibrated_profile.json'); save('calibration_report.json',report)
    model=HistoricalDemandModel.fit(normalized.get('zomato',()),hour_exposure=None,source='Zomato training only; exposure and courier pay unknown',source_sha256=digest)
    (OUT/'historical_model.json').write_text(model.model_dump_json(indent=2)+'\n')
    parameters=[]
    for p in profile.provenance:
        parameters.append({'parameter':p.parameter,'status':'synthetic_fallback' if p.fallback else p.classification,
            'source':p.source,'sample_size':p.sample_size,'transformation':p.transformation,
            'value_or_distribution':profile.model_dump(mode='json')[p.parameter],
            'limitations':p.fallback or ('straight-line km, no route detour; India dataset' if p.parameter=='order_distance_distribution' else 'selected training records, coverage unknown')})
    for param in ('vehicle_distribution','multiple_delivery_frequency'):
        parameters.append({'parameter':param,'status':'observed' if 'zomato' in contexts else 'synthetic_fallback',
            'source':'Zomato training','sample_size':sum(vehicles.values()) if param=='vehicle_distribution' and 'zomato' in contexts else len(multiples) if 'zomato' in contexts else 0,
            'transformation':'category counts' if param=='vehicle_distribution' else 'fraction multiple_deliveries > 0 among nonmissing values',
            'value_or_distribution':profile.model_dump(mode='json')[param],
            'limitations':'Descriptive only: vehicle fixed per evaluated shift; multiple deliveries is source metadata, not forced concurrent orders'})
    policy=StrategyPolicy(); buckets=[]
    zom=normalized.get('zomato',())
    for lo,hi in [(0,3),(3,6),(6,10),(10,100)]:
        times=[r.service_time_min for r in zom if r.distance_km is not None and lo<r.distance_km<=hi and r.service_time_min is not None]
        if len(times)>=30: buckets.append(SLABucket(distance_upper_km=hi,expected_min=float(np.mean(times)),p90_min=float(np.quantile(times,.9,method='higher')),sample_count=len(times)))
    policy=policy.model_copy(update={'sla_distance_buckets':tuple(buckets)})
    (OUT/'calibrated_policy.json').write_text(policy.model_dump_json(indent=2)+'\n')
    # Descriptive subgroup diagnostics make marginalized traffic/vehicle assumptions visible.
    subgroup=[]
    if 'zomato' in contexts:
        for field in ('Road_traffic_density','Type_of_vehicle'):
            for label, group in contexts['zomato'].groupby(field):
                values=pd.to_numeric(group['Time_taken (min)'],errors='coerce').dropna()
                subgroup.append({'field':field,'value':str(label),'n':len(values),
                                 'mean_min':float(values.mean()),'p90_min':float(values.quantile(.9,interpolation='higher'))})
    save('sla_subgroup_diagnostics.json',subgroup)
    save('sla_calibration.json',{'policy': [b.model_dump() for b in buckets],
        'formula':'max(current pickup + prep + delivery estimated minutes, empirical distance-bin P90 total delivery minutes); outside supported distances retain synthetic SLA',
        'fit':'training records only, >=30 samples/bin, nearest-rank P90',
        'limitations':['Historical prep unavailable in Zomato: order-to-pickup mixes travel/wait/prep and is not KPT.',
                       'Traffic and vehicle retained for subgroup diagnostics, marginalized in P90 because request has no observed traffic category; live travel estimates reflect configured vehicle/shocks.',
                       'Straight-line historical distance versus simulated leg km; transfer assumption.', 'Coverage on heldout CSV not used for tuning; P90 is empirical, not a universal guarantee.']})
    for name in ('base_reservation_wage','skip_penalty_mxn','cancellation_penalty_mxn','sla_time_multiplier','sla_buffer_min'):
        parameters.append({'parameter':name,'status':'assumed','source':'StrategyPolicy defaults','sample_size':0,'transformation':'none',
                           'value_or_distribution':getattr(policy,name),'limitations':'No source evidence; economic thresholds can be selected on tuning seeds only'})
    parameters.append({'parameter':'operating_cost_per_km','status':'assumed','source':'app/config/vehicles.py','sample_size':0,'transformation':'configured vehicle costs','value_or_distribution':{'moto':1.2,'car':3,'bike':.2},'limitations':'Not inferred from customer bills or cancellation rates'})
    parameters.append({'parameter':'sla_distance_buckets','status':'derived' if buckets else 'synthetic_fallback','source':'Zomato training','sample_size':sum(b.sample_count for b in buckets), 'transformation':'distance-bin nearest-rank P90 total duration', 'value_or_distribution':[b.model_dump() for b in buckets],'limitations':'See sla_calibration.json'})
    save('calibration_manifest.json',{'source_sha256':digest,'training_seeds':[],'sources':sources,'temporal_split':split,'parameters':parameters,
        'limitations':['No declared observation exposure: absolute arrivals and hourly demand multipliers remain synthetic. Timestamp frequencies are descriptive only.',
                       'No courier payout: historical revenue null; strategy uses neutral zero economic adjustment (not a historical earnings estimate).',
                       'Synthetic simulator costs, pay and grid remain assumptions; service distribution is descriptive, physics derives execution time.']})
    for p,d in raw_hashes.items():
        if sha256(Path(p).read_bytes()).hexdigest()!=d: raise RuntimeError('Raw data mutated')
    lines=['# Public data audit','', 'Raw CSV bytes verified unchanged. Audit runs before cleaning. No customer payment is courier payout.','']
    for name,audit in audits.items():
        lines.append(f"- {name}: {audit['rows']} rows; {audit['duplicates']} exact duplicates; training usable: {audit.get('usable_training_records','routing only')}.")
    lines+=['','Detailed columns, missingness, ranges, IQR outliers and anomalies: `data_audit_report.json`.','Mappings: `field_mapping.csv`. Cleaning: `data_cleaning_report.json`.','Split: `data_split_manifest.json`. Zones: `abstract_zones.json`. SLA: `sla_calibration.json`.','Exposure and payout unknown: no calibrated arrival rate or historical revenue.']
    (OUT/'DATA_AUDIT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'training':split,'routing':routing,'profile':profile.name},indent=2))


if __name__=='__main__': main()
