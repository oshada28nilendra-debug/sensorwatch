"""Single-sensor, fixed-grid retrospective fault analysis."""
import csv
import hashlib
import io
import json
import math
import time
from datetime import datetime, timedelta, timezone
import importlib.metadata
import numpy as np
from sklearn.ensemble import IsolationForest

WINDOW=5

def stamp(t):
    return t.astimezone(timezone.utc).isoformat().replace('+00:00','Z')

def date(text):
    try:
        value=datetime.fromisoformat(text.replace('Z','+00:00'))
        if value.tzinfo is None or value.utcoffset() is None: raise ValueError()
        return value.astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError) as exc:
        raise ValueError('Timestamps must be ISO 8601 with timezone, e.g. 2026-01-01T00:00:00Z.') from exc

def parse_csv(raw):
    if not raw or len(raw)>5*1024*1024: raise ValueError('CSV must contain data and be at most 5 MiB.')
    try:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),strict=True)
        if reader.fieldnames != ['timestamp','value']:
            raise ValueError('CSV header must be exactly timestamp,value.')
        rows=[];previous=None
        for line,row in enumerate(reader,2):
            if None in row or any(v is None for v in row.values()): raise ValueError(f'Row {line}: expected exactly two columns.')
            when=date(row['timestamp'].strip())
            if previous is not None and when<=previous: raise ValueError('Timestamps must be strictly increasing and unique; sort or deduplicate explicitly.')
            previous=when; text=row['value'].strip()
            try: value=float(text) if text else None
            except ValueError as exc: raise ValueError(f'Row {line}: invalid numeric value.') from exc
            if value is not None and (not math.isfinite(value) or abs(value)>1e12):
                raise ValueError(f'Row {line}: value must be finite, magnitude at most 1e12.')
            rows.append({'timestamp':stamp(when),'value':value})
            if len(rows)>10000: raise ValueError('Maximum 10,000 input rows.')
    except (UnicodeError,csv.Error) as exc: raise ValueError('CSV must be well-formed UTF-8.') from exc
    if not rows: raise ValueError('CSV has no readings.')
    return rows

def timeline(rows,cadence):
    if isinstance(cadence,bool) or not isinstance(cadence,(int,float)) or not math.isfinite(cadence) or not 0.001<=cadence<=86400:
        raise ValueError('Cadence must be finite, from 0.001 to 86400 seconds.')
    origin=date(rows[0]['timestamp']); by_index={}; last=-1
    for row in rows:
        offset=(date(row['timestamp'])-origin).total_seconds()/cadence; index=round(offset)
        if abs(offset-index)>1e-6 or index<=last: raise ValueError('Timestamps must align with the expected cadence grid without duplicates.')
        if index>=20000: raise ValueError('Expanded timeline exceeds 20,000 slots; check cadence.')
        last=index;by_index[index]=row
    return [{'timestamp':stamp(origin+timedelta(seconds=i*cadence)),
             'value':by_index[i]['value'] if i in by_index else None,
             'missing_kind':('blank' if by_index[i]['value'] is None else None) if i in by_index else 'absent'} for i in range(last+1)]

def metrics(truth,predicted):
    if len(truth)!=len(predicted): raise ValueError('Metric arrays must have equal lengths.')
    t=np.asarray(truth,dtype=bool);p=np.asarray(predicted,dtype=bool)
    tp=int((t&p).sum());fp=int((~t&p).sum());fn=int((t&~p).sum());tn=int((~t&~p).sum())
    precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
    return {'tp':tp,'fp':fp,'fn':fn,'tn':tn,'precision':precision,'recall':recall,
            'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,'evaluated':len(t)}

def features(rows):
    x=[];indices=[]
    for i in range(WINDOW-1,len(rows)):
        values=[r['value'] for r in rows[i-WINDOW+1:i+1]]
        if all(v is not None for v in values):
            x.append([values[-1],abs(values[-1]-values[-2]),float(np.std(values))]);indices.append(i)
    return np.asarray(x,dtype=float).reshape(-1,3),indices

def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,allow_nan=False).encode()).hexdigest()

def analyze(reference,observed,cadence=60,z_threshold=3.5,stuck_count=5,epsilon=1e-6):
    for name,value,lower,upper in [('z_threshold',z_threshold,.1,100),('epsilon',epsilon,0,1e6)]:
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lower<=value<=upper:
            raise ValueError(f'{name} must be finite between {lower} and {upper}.')
    if type(stuck_count) is not int or not 2<=stuck_count<=1000: raise ValueError('stuck_count must be an integer from 2 to 1000.')
    train=timeline(reference,cadence);rows=timeline(observed,cadence)
    if date(reference[-1]['timestamp'])>=date(observed[0]['timestamp']):
        raise ValueError('Reference timestamps must end before analysis begins; use a separate earlier reference period.')
    train_x,_=features(train)
    if len(train_x)<20: raise ValueError('Need at least 20 finite contiguous five-reading reference windows.')
    finite=np.array([r['value'] for r in train if r['value'] is not None]); median=float(np.median(finite))
    scale=float(1.4826*np.median(np.abs(finite-median)));method='MAD × 1.4826'
    if scale<1e-12:
        scale=float(np.std(finite));method='standard deviation fallback'
        if scale<1e-12: scale=max(abs(median)*1e-6,1e-6);method='absolute floor'
    for row in rows:
        score=abs(row['value']-median)/scale if row['value'] is not None else None
        row.update(robust_score=score,spike=bool(score is not None and score>z_threshold),stuck=False,
                   eligible=False,iforest_anomaly=None,iforest_score=None)
    # Mark every qualifying range-bounded window, including overlapping runs.
    from collections import deque
    minima,maxima=deque(),deque();left=0;marks=np.zeros(len(rows)+1,dtype=int)
    for right,row in enumerate(rows):
        if row['value'] is None:
            minima.clear();maxima.clear();left=right+1;continue
        value=row['value']
        while minima and rows[minima[-1]]['value']>=value:minima.pop()
        while maxima and rows[maxima[-1]]['value']<=value:maxima.pop()
        minima.append(right);maxima.append(right)
        while rows[maxima[0]]['value']-rows[minima[0]]['value']>epsilon:
            if minima[0]==left:minima.popleft()
            if maxima[0]==left:maxima.popleft()
            left+=1
        if right-left+1>=stuck_count:marks[left]+=1;marks[right+1]-=1
    for row,count in zip(rows,np.cumsum(marks)[:-1]):row['stuck']=bool(count>0)
    t=time.perf_counter()
    model=IsolationForest(n_estimators=100,contamination=.05,random_state=42,n_jobs=1).fit(train_x)
    fit_ms=(time.perf_counter()-t)*1000;x,indices=features(rows);t=time.perf_counter()
    if len(x):
        scores=-model.decision_function(x)
        for index,score in zip(indices,scores):rows[index].update(eligible=True,iforest_score=float(score),iforest_anomaly=bool(score>0))
    score_ms=(time.perf_counter()-t)*1000
    for row in rows: row['rule_anomaly']=row['spike'] or row['stuck']
    return {'schema_version':1,'reference_sha256':fingerprint(reference),'analysis_sha256':fingerprint(observed),
        'config':{'cadence_seconds':cadence,'z_threshold':z_threshold,'stuck_count':stuck_count,'epsilon':epsilon},
        'rules':{'reference_median':median,'reference_scale':scale,'scale_method':method},
        'model':{'name':'IsolationForest','seed':42,'trees':100,'contamination':.05,'fit_rows':len(train_x),
                 'features':['value','absolute previous delta','trailing 5-point population standard deviation'],'score':'negative decision_function; >0 flags anomaly'},
        'summary':{'slots':len(rows),'observed':sum(r['value'] is not None for r in rows),
            'missing':sum(r['missing_kind'] is not None for r in rows),'spikes':sum(r['spike'] for r in rows),
            'stuck':sum(r['stuck'] for r in rows),'eligible_numeric':len(indices),
            'iforest_flags':sum(r['iforest_anomaly'] is True for r in rows)},
        'timing_ms':{'fit':fit_ms,'score':score_ms},
        'versions':{n:importlib.metadata.version(n) for n in ['numpy','scikit-learn']},
        'warnings':['Retrospective flags require human review; not a production alarm system.',
                    'First four finite readings after start/missing slots have no model score; numeric comparison uses shared eligible rows.',
                    'Missing slots are checked only between the first and last supplied timestamps.'],
        'rows':rows}

def evaluate(report,labels):
    if not isinstance(labels,dict) or not isinstance(labels.get('description'),str) or not labels['description'].strip():
        raise ValueError('Labels need a nonempty dataset description.')
    mapping=labels.get('labels')
    if not isinstance(mapping,dict) or set(mapping)!={r['timestamp'] for r in report['rows']}:
        raise ValueError('Labels must cover every timeline slot exactly once using canonical UTC timestamps.')
    if any(x not in ['normal','spike','stuck','missing'] for x in mapping.values()): raise ValueError('Unknown fault label.')
    eligible=[r for r in report['rows'] if r['eligible']]
    truth=[mapping[r['timestamp']] in {'spike','stuck'} for r in eligible]
    result={'dataset_description':labels['description'],'labels_sha256':fingerprint(labels),
            'protocol':'Point-level, no event adjustment. Same finite five-point-window eligibility for both numeric methods; missing slots scored separately.',
            'numeric':{name:metrics(truth,[bool(r[key]) for r in eligible]) for name,key in [('rules','rule_anomaly'),('isolation_forest','iforest_anomaly')]},
            'missing':metrics([mapping[r['timestamp']]=='missing' for r in report['rows']],[r['missing_kind'] is not None for r in report['rows']]),
            'numeric_faults_excluded_by_warmup':sum(not r['eligible'] and mapping[r['timestamp']] in {'spike','stuck'} for r in report['rows'])}
    result['fault_recall']={fault:{name:metrics([True for r in eligible if mapping[r['timestamp']]==fault],
                        [bool(r[key]) for r in eligible if mapping[r['timestamp']]==fault])['recall']
                        for name,key in [('rules','rule_anomaly'),('isolation_forest','iforest_anomaly')]}
                          for fault in ['spike','stuck']}
    return result
