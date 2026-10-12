"""Deterministic synthetic fixture generator. No real sensor data."""
import csv
import io
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
from .core import stamp

def generate(seed=20261012):
    rng=np.random.default_rng(seed);ntrain=300;ntest=400;base=datetime(2026,10,1,tzinfo=timezone.utc)
    train=20+np.sin(np.arange(ntrain)/15)*.4+rng.normal(0,.3,ntrain)
    test=20+np.sin(np.arange(ntest)/15)*.4+rng.normal(0,.3,ntest)
    labels=['normal']*ntest
    for i in [30,75,120,175,225,275,330,370]:test[i]+=5 if i%2 else -5;labels[i]='spike'
    for start in [90,240]:test[start:start+14]=20.0;labels[start:start+14]=['stuck']*14
    absent=set(range(150,157));blank={200,201}
    for i in absent|blank:labels[i]='missing'
    def output(values,start,drop=set(),blanks=set()):
        out=io.StringIO(newline='');writer=csv.writer(out,lineterminator="\n");writer.writerow(['timestamp','value'])
        for i,v in enumerate(values):
            if i not in drop:writer.writerow([stamp(base+timedelta(minutes=start+i)),'' if i in blanks else f'{v:.6f}'])
        return out.getvalue().encode()
    truth={'description':f'SYNTHETIC seeded fixture {seed}: noisy stationary temperature-like signal, injected spikes, flat runs and missing slots. Not real-world validation.',
           'seed':seed,'labels':{stamp(base+timedelta(minutes=ntrain+i)):label for i,label in enumerate(labels)}}
    return output(train,0),output(test,ntrain,absent,blank),truth

def write_sample(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);train,test,labels=generate()
    (root/'reference.csv').write_bytes(train);(root/'readings.csv').write_bytes(test)
    (root/'labels.json').write_text(json.dumps(labels,indent=2)+'\n')

if __name__=='__main__':write_sample(Path(__file__).parent/'sample')
