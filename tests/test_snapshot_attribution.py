"""Exercise frozen models and staged publication without touching live artifacts."""
import os
import subprocess
import sys
import pytest


@pytest.mark.parametrize('market', ['us', 'korea'])
@pytest.mark.parametrize('fail', [False, True])
def test_attribution_refresh_and_endpoints(tmp_path, market, fail):
    script = r'''
import hashlib,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from src.operations import refresh, store
from src.operations.worker import build
from src.explainability import attribution
from src.api import main as api
market,fail=sys.argv[1],sys.argv[2]=='True'
model_path=api.MODELS_DIR/'xgboost_latest.joblib' if market=='us' else api.KOREA_MODEL_DIR/'xgboost_10d_latest.joblib'
before=hashlib.sha256(model_path.read_bytes()).hexdigest()
original_explain=attribution.explain
seen=[]
def capture(model,row,**kwargs):
    seen.append(row.copy())
    return original_explain(model,row,**kwargs)
attribution.explain=capture
stage=store.root()/'staging'/'test';stage.mkdir(parents=True)
spec=refresh.stage_inputs(market,stage,refresh.legacy(market),[],'legacy-cache','2026-10-14')
build(market,stage)
payload=json.loads((stage/'snapshot.json').read_text())
assert len(seen)==1 and len(seen[0])==1
assert seen[0].index[0].strftime('%Y-%m-%d')==spec['common_date']==payload['last_updated']
a=payload['attribution']
assert a['feature_row_sha256']==hashlib.sha256(seen[0].to_csv().encode()).hexdigest()
assert a['model_sha256']==before
for d in a['top_drivers']:
    assert d['feature_value']==float(seen[0][d['feature']].iloc[0])
# The existing top-eight contract contains drivers for all three groups in real fixtures.
for prefix in [('SPY_' if market=='us' else 'KOSPI200_'),('VIX_' if market=='us' else 'VKOSPI_'),'Credit_']:
    assert any(d['feature'].startswith(prefix) for d in a['top_drivers'])
with store.database() as db:
    db.execute("INSERT INTO jobs (job_id,market,trigger,started_at,status) VALUES ('test',?,'manual',?,'RUNNING')",(market,store.utcnow()))
sid=store.publish('test',market,payload)
client=TestClient(api.app)
base='/api' if market=='us' else '/api/korea'
assert client.get(base+'/latest').status_code==200
assert client.get(base+'/shap').json()==a
assert client.get(base+'/historical').status_code==200
if market=='korea':assert client.get(base+'/validation').status_code==200
for key,bad in [('date','1900-01-01'),('observation_date','1900-01-01'),('common_feature_date','1900-01-01'),('model_sha256','wrong'),('model','wrong'),('market','wrong')]:
    changed={**payload,'attribution':{**a,key:bad}}
    try:store.publish('test',market,changed)
    except ValueError:pass
    else:raise AssertionError('Accepted inconsistent '+key)
    assert store.snapshot(market)['snapshot_id']==sid
if fail:
    def broken(*args,**kwargs):raise RuntimeError('injected TreeSHAP failure')
    attribution.explain=broken
    # Run the real refresh path with existing cached inputs, injecting only the worker launcher.
    refresh.expected=lambda _:('2026-10-14','2026-10-15T00:00:00+00:00')
    def run(args,**kwargs):
        try:build(market,args[-1])
        except RuntimeError as exc:
            assert 'TreeSHAP failure' in str(exc)
            assert not (Path(args[-1])/'snapshot.json').exists()
            return subprocess.CompletedProcess(args,1,'',str(exc))
        raise AssertionError('Unexpected success')
    import subprocess
    refresh.subprocess.run=run
    report=refresh.refresh(market,adopt_local=True)
    assert report['status']=='ERROR' and not report['snapshot_published']
    assert store.snapshot(market)['snapshot_id']==sid
    assert client.get(base+'/shap').json()==a
assert hashlib.sha256(model_path.read_bytes()).hexdigest()==before
'''
    env = dict(os.environ, MARKET_OPERATIONS_DIR=str(tmp_path/'operations'))
    result = subprocess.run([sys.executable, '-c', script, market, str(fail)], env=env,
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-5000:]


def test_read_rejects_mismatched_attribution(monkeypatch):
    from fastapi import HTTPException
    from src.operations import service
    snapshot = {'last_updated': '2026-10-13', 'common_feature_date': '2026-10-13',
                'model_sha256': 'frozen', 'feature_count': 17, 'source_provenance': 'provider-validated'}
    attribution = {'date': '2026-10-13', 'observation_date': '2026-10-13',
                   'common_feature_date': '2026-10-13', 'model_sha256': 'frozen',
                   'model': 'XGBoost', 'market': 'korea', 'feature_count': 17,
                   'source_provenance': 'provider-validated',
                   'top_drivers': [{'feature': 'Credit_Level', 'feature_value': 1., 'shap_value': .2}]}
    monkeypatch.setattr(service, 'snapshot', lambda _: {'payload': {**snapshot, 'attribution': attribution}})
    assert service.current_attribution('korea') == attribution
    for key, value in [('date', '2026-10-02'), ('model_sha256', 'different')]:
        original = attribution[key]
        attribution[key] = value
        with pytest.raises(HTTPException) as error:
            service.current_attribution('korea')
        assert error.value.status_code == 503
        attribution[key] = original
    monkeypatch.setattr(service, 'snapshot', lambda _: {'payload': snapshot})
    with pytest.raises(HTTPException):
        service.current_attribution('korea')
