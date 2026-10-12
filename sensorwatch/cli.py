import argparse
import json
from pathlib import Path
from .core import parse_csv,analyze,evaluate

def main():
    parser=argparse.ArgumentParser(description='Inspect single-sensor timestamped CSV faults locally.')
    commands=parser.add_subparsers(dest='command',required=True)
    serve=commands.add_parser('serve');serve.add_argument('--port',type=int,default=8767)
    p=commands.add_parser('analyze');p.add_argument('--reference',type=Path,required=True);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--labels',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cadence',type=float,default=60);p.add_argument('--z-threshold',type=float,default=3.5)
    p.add_argument('--stuck-count',type=int,default=5);p.add_argument('--epsilon',type=float,default=1e-6)
    args=parser.parse_args()
    try:
        if args.command=='serve':
            from .web import create_app
            create_app().run(host='127.0.0.1',port=args.port,debug=False,threaded=False);return
        report=analyze(parse_csv(args.reference.read_bytes()),parse_csv(args.input.read_bytes()),args.cadence,args.z_threshold,args.stuck_count,args.epsilon)
        if args.labels:
            raw=args.labels.read_bytes()
            if len(raw)>5*1024*1024:raise ValueError('Labels exceed 5 MiB.')
            report['evaluation']=evaluate(report,json.loads(raw))
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(args.output)
    except (ValueError,OSError) as exc:parser.exit(2,f'Error: {exc}\n')

if __name__=='__main__':main()
