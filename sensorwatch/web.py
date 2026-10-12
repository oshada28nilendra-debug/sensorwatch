import json
from pathlib import Path
from flask import Flask,jsonify,request,render_template
from werkzeug.exceptions import HTTPException
from .core import parse_csv,analyze,evaluate

SAMPLE=Path(__file__).parent/'sample'
def create_app():
    app=Flask(__name__);app.config['MAX_CONTENT_LENGTH']=16*1024*1024
    @app.before_request
    def guard():
        if request.host.split(':')[0] not in {'localhost','127.0.0.1'}:return jsonify(error='Use localhost or 127.0.0.1.'),403
        if request.method=='POST' and (request.headers.get('X-SensorWatch')!='local' or (request.headers.get('Origin') and request.headers['Origin']!=request.host_url.rstrip('/'))):
            return jsonify(error='Local requests only.'),403
    @app.after_request
    def headers(response):
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'"
        response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff';return response
    @app.errorhandler(ValueError)
    def invalid(e):return jsonify(error=str(e)),400
    @app.errorhandler(HTTPException)
    def http(e):return jsonify(error=e.description),e.code
    @app.get('/')
    def home():return render_template('index.html')
    @app.post('/api/analyze')
    def run():
        sample=request.form.get('sample')=='1'
        def data(name):
            f=request.files.get(name)
            if not f:raise ValueError(f'Upload {name} CSV.')
            return f.read()
        reference=(SAMPLE/'reference.csv').read_bytes() if sample else data('reference')
        readings=(SAMPLE/'readings.csv').read_bytes() if sample else data('readings')
        try:
            config={'cadence':float(request.form.get('cadence',60)),'z_threshold':float(request.form.get('z_threshold',3.5)),
                    'stuck_count':int(request.form.get('stuck_count',5)),'epsilon':float(request.form.get('epsilon',1e-6))}
        except ValueError as exc:raise ValueError('Detector settings must be numeric; stuck count must be an integer.') from exc
        report=analyze(parse_csv(reference),parse_csv(readings),**config)
        raw=(SAMPLE/'labels.json').read_bytes() if sample else request.files['labels'].read() if request.files.get('labels') else None
        if raw is not None:
            if len(raw)>5*1024*1024:raise ValueError('Labels exceed 5 MiB.')
            try:labels=json.loads(raw)
            except (ValueError,UnicodeError) as exc:raise ValueError('Labels must be UTF-8 JSON.') from exc
            report['evaluation']=evaluate(report,labels)
        report['dataset']='Synthetic seeded demo' if sample else 'User supplied'
        return jsonify(report)
    return app
