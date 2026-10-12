import json
from datetime import datetime, timedelta, timezone
import numpy as np
import pytest
from sensorwatch.core import parse_csv,timeline,metrics,analyze,evaluate

def csv(values, start=0):
    base=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=start)
    return ('timestamp,value\n'+'\n'.join(f'{(base+timedelta(minutes=i)).isoformat()},{"" if x is None else x}' for i,x in enumerate(values))).encode()

def test_import_and_missing():
    rows=parse_csv(b'\xef\xbb\xbftimestamp,value\r\n2026-01-01T01:00:00+01:00,2\r\n2026-01-01T00:01:00Z,\r\n')
    assert rows[0]['timestamp']=='2026-01-01T00:00:00Z'
    assert rows[1]['value'] is None

@pytest.mark.parametrize('raw', [b'',b'timestamp,x\n',b'\xff',b'timestamp,value\n2026-01-01,1',b'timestamp,value\n2026-01-01T00:00:00Z,nan',b'timestamp,value\n2026-01-01T00:00:00Z,inf',csv([1,2])+b'2026-01-01T00:00:00Z,3\n',b'timestamp,value,value\nx,1,2',b'timestamp,value\n2026-01-01T00:00:00Z,1,extra'])
def test_bad_import(raw):
    with pytest.raises(ValueError):parse_csv(raw)

def test_grid_expansion_and_alignment():
    rows=parse_csv(csv([1,2,3,4])); del rows[1]
    expanded=timeline(rows,60)
    assert len(expanded)==4 and expanded[1]['missing_kind']=='absent'
    rows[1]['timestamp']='2026-01-01T00:02:01Z'
    with pytest.raises(ValueError,match='grid'):timeline(rows,60)
    with pytest.raises(ValueError):timeline(parse_csv(csv([1,2])),0)

def test_metrics_known_and_undefined():
    m=metrics([True,True,False,False],[True,False,True,False])
    assert m['precision']==.5 and m['recall']==.5 and m['tp']==1 and m['fp']==1
    assert metrics([False],[False])['precision'] is None
    assert metrics([False],[False])['recall'] is None

def test_rules_stuck_gap_and_common_eligibility():
    rng=np.random.default_rng(4); train=parse_csv(csv(rng.normal(20,1,200)))
    values=list(rng.normal(20,1,70));values[12]=100;values[30:38]=[20]*8;values[45]=None
    report=analyze(train,parse_csv(csv(values,300)))
    rows=report['rows']
    assert rows[12]['spike'] and all(rows[i]['stuck'] for i in range(30,38))
    assert rows[45]['missing_kind']=='blank'
    assert all(not rows[i]['eligible'] for i in range(45,50)) and rows[50]['eligible']
    assert report['model']['fit_rows']==196
    assert all(r['iforest_anomaly'] is None for r in rows if not r['eligible'])

def test_constant_reference_disclosed_and_no_nonfinite_report():
    r=analyze(parse_csv(csv([7]*30)),parse_csv(csv([7]*10,100)))
    assert r['rules']['scale_method']=='absolute floor'
    json.dumps(r,allow_nan=False)

@pytest.mark.parametrize('kwargs',[{'z_threshold':0},{'epsilon':-1},{'stuck_count':1},{'cadence':float('nan')}])
def test_bad_configuration(kwargs):
    with pytest.raises(ValueError):analyze(parse_csv(csv([1]*30)),parse_csv(csv([1]*10,100)),**kwargs)

def test_reference_too_short():
    with pytest.raises(ValueError,match='reference'):analyze(parse_csv(csv([1]*10)),parse_csv(csv([1]*10,100)))

def test_overlapping_flat_windows_do_not_lose_valid_run():
    train=parse_csv(csv(np.arange(30)))
    report=analyze(train,parse_csv(csv([0,.9,1.1,1.2,1.3,1.4,4,5],100)),epsilon=.6,stuck_count=5)
    assert not report['rows'][0]['stuck']
    assert all(r['stuck'] for r in report['rows'][1:6])

def test_gap_breaks_stuck_run_and_no_score_without_five_values():
    r=analyze(parse_csv(csv(np.arange(30))),parse_csv(csv([7,7,7,None,7,7,7],100)))
    assert not any(x['stuck'] for x in r['rows'])
    assert r['summary']['eligible_numeric']==0

def test_reference_overlap_rejected():
    with pytest.raises(ValueError,match='Reference timestamps'):
        analyze(parse_csv(csv(np.arange(30))),parse_csv(csv(np.arange(30))))

def test_evaluation_coverage_and_shared_denominator():
    from sensorwatch.sample_data import generate
    train,test,labels=generate();r=analyze(parse_csv(train),parse_csv(test));e=evaluate(r,labels)
    assert e['numeric']['rules']['evaluated']==e['numeric']['isolation_forest']['evaluated']==379
    assert e['missing']['tp']==9 and e['numeric_faults_excluded_by_warmup']==0
    assert e['dataset_description'].startswith('SYNTHETIC')
    broken=json.loads(json.dumps(labels));broken['labels'].pop(next(iter(broken['labels'])))
    with pytest.raises(ValueError,match='every timeline'):evaluate(r,broken)
    broken=json.loads(json.dumps(labels));broken['labels'][next(iter(broken['labels']))]='missing'
    inconsistent=evaluate(r,broken)
    assert inconsistent['missing']['fn']==1 and inconsistent['missing']['recall']==.9
    with pytest.raises(ValueError):evaluate(r,[])

def test_seed_reproducibility_and_model_determinism():
    from sensorwatch.sample_data import generate
    assert generate()==generate()
    a,b,_=generate(7);r=analyze(parse_csv(a),parse_csv(b));again=analyze(parse_csv(a),parse_csv(b))
    assert r['rows']==again['rows']

def test_limits_and_blank_reference():
    with pytest.raises(ValueError):parse_csv(b'x'*(5*1024*1024+1))
    with pytest.raises(ValueError):parse_csv(csv([1]*10001))
    with pytest.raises(ValueError,match='20,000'):timeline(parse_csv(csv([1,2])),.001)
    with pytest.raises(ValueError,match='reference'):analyze(parse_csv(csv([None]*30)),parse_csv(csv([1]*20,100)))
