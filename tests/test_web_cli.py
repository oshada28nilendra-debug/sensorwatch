import io
import json
import subprocess
import sys
from pathlib import Path
import pytest
from sensorwatch.web import create_app,SAMPLE

@pytest.fixture
def client():return create_app().test_client()

def post(client,data):return client.post('/api/analyze',data=data,headers={'X-SensorWatch':'local'})

def test_demo_and_guards(client):
    assert client.get('/').status_code==200
    assert client.get('/',headers={'Host':'evil.test'}).status_code==403
    assert client.post('/api/analyze').status_code==403
    assert client.post('/api/analyze',headers={'Origin':'https://evil.test','X-SensorWatch':'local'}).status_code==403
    r=post(client,{'sample':'1'});assert r.status_code==200
    assert r.json['summary']['missing']==9 and r.json['evaluation']['numeric']['rules']['evaluated']==379
    assert r.headers['Cache-Control']=='no-store'

@pytest.mark.parametrize('data',[{}, {'sample':'1','cadence':'x'}, {'sample':'1','cadence':'nan'},{'sample':'1','stuck_count':'2.5'}])
def test_invalid_requests(client,data):assert post(client,data).status_code==400

def test_real_upload_and_malformed_labels(client):
    def data():return {'reference':(io.BytesIO((SAMPLE/'reference.csv').read_bytes()),'train.csv'),
                       'readings':(io.BytesIO((SAMPLE/'readings.csv').read_bytes()),'test.csv')}
    r=post(client,data());assert r.status_code==200 and 'evaluation' not in r.json
    d=data();d['labels']=(io.BytesIO(b'{broken'),'labels.json');assert post(client,d).status_code==400

def test_oversized_http(client):
    r=client.post('/api/analyze',data=b'x'*(16*1024*1024+1),headers={'X-SensorWatch':'local'},content_type='application/octet-stream')
    assert r.status_code==413

def test_cli_export_and_error(tmp_path):
    output=tmp_path/'report.json'
    p=subprocess.run([sys.executable,'-m','sensorwatch.cli','analyze','--reference',str(SAMPLE/'reference.csv'),'--input',str(SAMPLE/'readings.csv'),'--labels',str(SAMPLE/'labels.json'),'--output',str(output)],capture_output=True,text=True)
    assert p.returncode==0 and json.loads(output.read_text())['evaluation']['missing']['tp']==9
    p=subprocess.run([sys.executable,'-m','sensorwatch.cli','analyze','--reference','missing.csv','--input','missing.csv','--output',str(output)],capture_output=True,text=True)
    assert p.returncode==2 and 'Error:' in p.stderr
