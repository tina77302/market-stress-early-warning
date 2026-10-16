"""Operational safety invariants; all storage isolated from real users/data."""
import fcntl
import json
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import pytest
from src.operations import store, refresh as refresh_module, scheduler, service
from src.operations.calendar import expected
from src.operations.providers import Providers
from src.operations.validation import validate_series, validate_features, ValidationFailure, TransientProviderError


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('MARKET_OPERATIONS_DIR',str(tmp_path/'operations'))


def job(market='us'):
    with store.database() as db:
        db.execute("INSERT INTO jobs (job_id,market,trigger,started_at,status) VALUES (?,?, 'manual',?,'RUNNING')",('test-'+market,market,store.utcnow()))
    return 'test-'+market


def payload(date='2026-10-08'):
    return {'last_updated':date,'risk_score_10d':13.2,'market_stress_index':0.2,'source_provenance':'provider-validated','input_series':[
        {'series':name,'provider':'fixture','latest_observation_date':date,'retrieved_at':'2026-10-12T00:00:00+00:00'} for name in ['SPY','VIX','DBAA','DGS10']]}


def frame(values=(1.0,2.0,3.0),column='SPY'):
    return pd.DataFrame({column:values},index=pd.date_range('2020-01-01',periods=len(values)))


@pytest.mark.parametrize('bad',[
    pd.DataFrame(),frame((1.0,np.inf,2.0)),frame((1.0,None,2.0)),frame((1.0,-1.0,2.0)),frame(('1','2','3')),
    frame().set_axis(pd.DatetimeIndex(['2020-01-01','2020-01-01','2020-01-03'])),frame().iloc[::-1],
    frame().set_axis(pd.date_range('2099-01-01',periods=3)),
])
def test_invalid_series_rejected(bad):
    with pytest.raises(ValidationFailure):validate_series(bad,'SPY',positive=True)


def test_real_crash_or_volatility_spike_not_rejected():
    assert validate_series(frame((100.0,10.0,900.0)),'SPY',positive=True)=='2020-01-03'


def test_retry_transient_is_bounded_and_recorded():
    jid=job();delays=[];p=Providers(jid,sleep=delays.append)
    def fail():raise TransientProviderError('timeout')
    with pytest.raises(TransientProviderError):p.call('SPY',fail)
    assert delays==[1,2]
    assert [a['attempt_count'] for a in store.history()[0]['attempts']]==[1,2,3]


def test_permanent_validation_not_retried():
    jid=job();p=Providers(jid,sleep=lambda _:pytest.fail('permanent retry'))
    def fail():raise ValidationFailure('wrong units')
    with pytest.raises(ValidationFailure):p.call('DBAA',fail)
    assert len(store.history()[0]['attempts'])==1


def test_success_after_transient_failure_records_both():
    jid=job();p=Providers(jid,sleep=lambda _:None);calls=[]
    def fetch():
        calls.append(True)
        if len(calls)==1:raise TransientProviderError('rate limit')
        return frame()
    result,retrieved=p.call('SPY',fetch)
    assert retrieved and len(result)==3
    assert [a['status'] for a in store.history()[0]['attempts']]==['ERROR','SUCCESS']


def test_publish_atomic_idempotent_and_regression_guard():
    jid=job();original=payload();sid=store.publish(jid,'us',original)
    assert store.publish(jid,'us',original)==sid
    with store.database() as db:assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]==1
    with pytest.raises(ValueError):store.publish(jid,'us',payload('2026-10-07'))
    with pytest.raises(ValueError):store.publish(jid,'us',{**original,'risk_score_10d':float('nan')})
    assert store.snapshot('us')['snapshot_id']==sid
    assert store.history()[0]['snapshot_published']==1


def test_transaction_failure_keeps_pointer(monkeypatch):
    jid=job();sid=store.publish(jid,'us',payload())
    with store.database() as db:
        db.execute("CREATE TRIGGER abort_pointer BEFORE UPDATE ON current_snapshots BEGIN SELECT RAISE(ABORT,'test failure'); END;")
    with pytest.raises(Exception):store.publish(jid,'us',payload('2026-10-09'))
    assert store.snapshot('us')['snapshot_id']==sid
    with store.database() as db:assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]==1


def test_failed_refresh_attempts_every_series_keeps_lkg(monkeypatch):
    jid=job();sid=store.publish(jid,'us',payload())
    monkeypatch.setattr(refresh_module,'seeds',lambda _: {})
    monkeypatch.setattr(refresh_module,'expected',lambda _:('2026-10-09','2026-10-10T08:00:00+00:00'))
    class FailProviders:
        def __init__(self,_):self.counts={}
        def yahoo(self,name,date):self.counts[name]=1;raise ValidationFailure('fixture unavailable')
        fred=yahoo
    report=refresh_module.refresh('us',providers_factory=FailProviders)
    assert len(report['series'])==4 and not report['snapshot_published']
    assert store.snapshot('us')['snapshot_id']==sid
    assert store.history()[0]['status']=='ERROR'
    with store.database() as db:assert db.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]>=1


def test_concurrent_refresh_cannot_run():
    store.root().mkdir(parents=True)
    with open(store.root()/'us.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert refresh_module.refresh('us')['status']=='ALREADY_RUNNING'
    assert not store.history()


def test_common_date_never_current_fill(tmp_path):
    dates=pd.bdate_range('2023-01-02',periods=500)
    frames={name:pd.DataFrame({name:np.arange(500,dtype=float)+10},index=dates) for name in ['SPY','VIX','DBAA','DGS10']}
    frames['DBAA'].iloc[-1]=np.nan
    frames['DGS10'].iloc[-1]=np.nan
    stage=tmp_path/'stage';stage.mkdir()
    spec=refresh_module.stage_inputs('us',stage,frames,[],'provider-validated','2026-10-09')
    assert spec['common_date']==dates[-2].strftime('%Y-%m-%d')
    raw=pd.read_csv(stage/'raw_market_data.csv')
    assert raw.iloc[-1]['Date']==spec['common_date']


def test_korea_gap_cannot_silently_shorten_rolling_calendar(tmp_path):
    dates=pd.bdate_range('2023-01-02',periods=500)
    frames={name:pd.DataFrame({name:np.arange(500,dtype=float)+10},index=dates) for name in refresh_module.SERIES['korea']}
    frames['VKOSPI'].iloc[300]=np.nan
    with pytest.raises(ValidationFailure,match='Missing Korea input'):
        refresh_module.stage_inputs('korea',tmp_path,frames,[],'provider-validated','2026-10-09')


def test_incomplete_features_rejected():
    with pytest.raises(ValidationFailure):validate_features(frame(),'SPY VIX'.split(),'2020-01-03')
    with pytest.raises(ValidationFailure):validate_features(frame(),['SPY'],'2020-01-04')


def test_holiday_and_incomplete_session():
    # Korean Hangul Day (Oct 9) is a holiday; Oct 12's session is not yet due at 08:38 UTC.
    now=datetime(2026,10,12,8,38,tzinfo=timezone.utc)
    assert expected('korea',now)[0]=='2026-10-08'
    assert expected('us',now)[0]=='2026-10-09'
    assert expected('us',datetime(2026,7,4,15,tzinfo=timezone.utc))[0]=='2026-07-02'


def test_health_independent_source_dates_and_scheduler(monkeypatch):
    jid=job();data=payload('2026-10-09');data['input_series'][-1]['latest_observation_date']='2026-10-08'
    store.publish(jid,'us',data)
    monkeypatch.setattr(service,'expected',lambda *args:('2026-10-09','2026-10-10T08:00:00+00:00'))
    result=service.health('us',datetime(2026,10,12,tzinfo=timezone.utc))
    assert not result['is_current'] and result['input_series'][-1]['status']=='STALE'
    assert result['scheduler']['status']=='MISSED'


def test_startup_catchup_and_throttle(monkeypatch):
    monkeypatch.setattr(scheduler,'expected',lambda *args:('2026-10-09','2026-10-10T08:00:00+00:00'))
    calls=[]
    monkeypatch.setattr(scheduler,'refresh',lambda market,trigger:calls.append((market,trigger)) or {'status':'SUCCESS'})
    scheduler.tick()
    assert [m for m,t in calls]==['us','korea']
    with store.database() as db:
        for market in ['us','korea']:
            db.execute("INSERT INTO jobs (job_id,market,trigger,expected_date,started_at,status) VALUES (?,?, 'startup-catch-up','2026-10-09',?,'ERROR')",('recent-'+market,market,store.utcnow()))
    calls.clear();scheduler.tick();assert not calls


def test_payload_integrity_check():
    jid=job();store.publish(jid,'us',payload())
    with store.database() as db:db.execute("UPDATE snapshots SET payload='{}'")
    with pytest.raises(ValueError,match='integrity'):store.snapshot('us')


def test_empty_response_retry_and_timeout_classification(monkeypatch):
    import requests
    jid=job();p=Providers(jid,sleep=lambda _:None)
    def fail():raise requests.Timeout('https://provider/private-secret')
    with pytest.raises(TransientProviderError):p.call('Korea_Treasury_3Y',fail)
    attempts=store.history()[0]['attempts']
    assert len(attempts)==3
    assert all('private-secret' not in a['error_message'] for a in attempts)


def test_no_snapshot_api_fails_closed():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:service.current_payload('us')
    assert error.value.status_code==503


@pytest.mark.parametrize('market',['us','korea'])
@pytest.mark.parametrize('failure',['timeout','exception','empty','malformed','missing','numeric','stale','feature','inference'])
def test_refresh_failure_matrix_preserves_each_market_lkg(monkeypatch,market,failure):
    import requests
    from types import SimpleNamespace
    jid=job(market); old=payload();old['input_series']=[{'series':n,'latest_observation_date':'2026-10-08','retrieved_at':store.utcnow()} for n in refresh_module.SERIES[market]]
    sid=store.publish(jid,market,old)
    monkeypatch.setattr(refresh_module,'expected',lambda _:('2026-10-09','2026-10-10T08:00:00+00:00'))
    monkeypatch.setattr(refresh_module,'seeds',lambda _: {})
    dates=pd.bdate_range(end='2026-10-09',periods=500)
    class FixtureProviders:
        def __init__(self,_):self.counts={}
        def yahoo(self,name,date,*args):
            self.counts[name]=1
            if name==refresh_module.SERIES[market][0]:
                if failure=='timeout':raise requests.Timeout('fixture timeout')
                if failure=='exception':raise RuntimeError('fixture exception')
                if failure=='empty':return pd.DataFrame(),store.utcnow()
                if failure=='malformed':return 'invalid',store.utcnow()
                if failure=='missing':return pd.DataFrame({'other':[1.]},index=dates[:1]),store.utcnow()
                if failure=='numeric':return pd.DataFrame({name:[np.inf]},index=dates[:1]),store.utcnow()
                if failure=='stale':return pd.DataFrame({name:np.arange(490,dtype=float)+10},index=dates[:490]),store.utcnow()
            return pd.DataFrame({name:np.arange(500,dtype=float)+10},index=dates),store.utcnow()
        fred=yahoo;krx=yahoo;ecos=yahoo
    def worker(*args,**kwargs):
        stage=store.root()/'staging'/store.history()[0]['job_id']
        (stage/'calculation.log').write_text(f'{failure} failed')
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(refresh_module.subprocess,'run',worker)
    result=refresh_module.refresh(market,providers_factory=FixtureProviders)
    assert result['status']=='ERROR' and not result['snapshot_published']
    assert store.snapshot(market)['snapshot_id']==sid
    assert store.history(market,1)[0]['finished_at']
    assert not service.health(market)['is_current']


@pytest.mark.parametrize('market',['us','korea'])
@pytest.mark.parametrize('alert_failure',[False,True])
def test_successful_lifecycle_and_duplicate_content(monkeypatch,market,alert_failure):
    from types import SimpleNamespace
    monkeypatch.setattr(refresh_module,'expected',lambda _:('2026-10-12','2026-10-13T08:00:00+00:00'))
    monkeypatch.setattr(refresh_module,'seeds',lambda _: {})
    if alert_failure:
        monkeypatch.setattr(refresh_module.alerts,'emit',lambda *a: (_ for _ in ()).throw(RuntimeError('outbox unavailable')))
    dates=pd.bdate_range(end='2026-10-09',periods=500)
    class FixtureProviders:
        def __init__(self,_):self.counts={}
        def yahoo(self,name,date,*args):
            self.counts[name]=1
            return pd.DataFrame({name:np.arange(500,dtype=float)+10},index=dates),store.utcnow()
        fred=yahoo;krx=yahoo;ecos=yahoo
    def worker(args,**kwargs):
        from pathlib import Path
        stage=Path(args[-1]);spec=json.loads((stage/'inputs.json').read_text())
        result={**payload('2026-10-09'),'input_series':spec['series'],'artifact_directory':str(stage),'anomalies':[],'model_inference_at':store.utcnow()}
        (stage/'snapshot.json').write_text(json.dumps(result))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(refresh_module.subprocess,'run',worker)
    first=refresh_module.refresh(market,providers_factory=FixtureProviders)
    sid=store.snapshot(market)['snapshot_id']
    second=refresh_module.refresh(market,providers_factory=FixtureProviders)
    assert first['status']==second['status']=='SUCCESS'
    assert store.snapshot(market)['snapshot_id']==sid
    assert all(j['report']['series'] and j['snapshot_published'] for j in store.history(market))
    with store.database() as db:assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]==1


def test_delayed_expires_when_next_session_due(monkeypatch):
    jid=job();store.publish(jid,'us',payload())
    with store.database() as db:db.execute("UPDATE jobs SET expected_date='2026-10-09' WHERE job_id=?",(jid,))
    monkeypatch.setattr(service,'expected',lambda *a:('2026-10-09','2026-10-10T08:00:00+00:00'))
    assert service.health('us')['status']=='DELAYED'
    assert all(s['status']=='DELAYED' for s in service.health('us')['input_series'])
    monkeypatch.setattr(service,'expected',lambda *a:('2026-10-12','2026-10-13T08:00:00+00:00'))
    assert service.health('us')['status']=='STALE'


def test_missing_required_metadata_cannot_claim_current(monkeypatch):
    jid=job();data=payload();data['input_series']=data['input_series'][:1];store.publish(jid,'us',data)
    monkeypatch.setattr(service,'expected',lambda *a:('2026-10-08','2026-10-09T08:00:00+00:00'))
    assert not service.health('us')['is_current']


def test_timezone_and_us_dst():
    from zoneinfo import ZoneInfo
    summer=datetime(2026,7,8,8,tzinfo=timezone.utc)
    winter=datetime(2026,12,9,9,tzinfo=timezone.utc)
    assert expected('us',summer)[1].endswith('08:00:00+00:00')
    assert expected('us',winter)[1].endswith('09:00:00+00:00')
    assert expected('us',summer)==expected('us',summer.astimezone(ZoneInfo('Asia/Seoul')))
    with pytest.raises(ValueError):expected('us',summer.replace(tzinfo=None))


def test_scheduler_distinguishes_failed_run_and_missed_run(monkeypatch):
    monkeypatch.setattr(scheduler,'expected',lambda *a:('2026-10-09','2026-10-10T08:00:00+00:00'))
    with store.database() as db:
        db.execute("INSERT INTO jobs (job_id,market,trigger,expected_date,started_at,status) VALUES ('old','us','startup-catch-up','2026-10-09',?,'ERROR')",((datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),))
    calls=[];monkeypatch.setattr(scheduler,'refresh',lambda market,trigger:calls.append((market,trigger)) or {})
    scheduler.tick()
    assert calls==[('us','scheduled-retry'),('korea','startup-catch-up')]


def test_interrupted_job_recovered_under_lock(monkeypatch):
    job();monkeypatch.setattr(refresh_module,'seeds',lambda _: (_ for _ in ()).throw(ValidationFailure('seed missing')))
    refresh_module.refresh('us')
    recovered=next(j for j in store.history() if j['job_id']=='test-us')
    assert recovered['status']=='ERROR' and recovered['error_type']=='InterruptedJob'


def test_api_metadata_and_health(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.main import app
    for market in ['us','korea']:
        jid=job(market);store.publish(jid,market,payload())
    client=TestClient(app)
    for route in ['/api/latest','/api/korea/latest']:
        response=client.get(route)
        assert response.status_code==200
        result=response.json()
        assert result['market_observation_date']==result['last_updated']
        assert 'data_retrieved_at' in result and 'model_inference_at' in result
        assert 'artifact_directory' not in result
        assert result['data_health']['last_known_good_date']==result['last_updated']
    assert client.get('/api/data-health').status_code==200
    assert client.get('/api/admin/data-health').status_code==401


def test_exchange_close_and_publication_readiness_are_distinct():
    from src.operations.calendar import latest_closed
    now=datetime(2026,10,14,0,15,tzinfo=timezone.utc)
    assert expected('us',now)[0]=='2026-10-12'
    assert latest_closed('us',now)=='2026-10-13'
    assert latest_closed('korea',now)=='2026-10-13'


def test_actual_refresh_collision_and_independent_markets(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    entered=threading.Event();release=threading.Event()
    def seed(market):
        if market=='us':
            entered.set();assert release.wait(10)
        raise ValidationFailure('fixture seed unavailable')
    monkeypatch.setattr(refresh_module,'seeds',seed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        running=pool.submit(refresh_module.refresh,'us',trigger='scheduled-retry')
        assert entered.wait(10)
        try:
            collision=refresh_module.refresh('us',trigger='manual')
            assert collision['status']=='ALREADY_RUNNING'
            assert refresh_module.refresh('korea')['status']=='ERROR'
        finally:release.set()
        assert running.result()['status']=='ERROR'
    assert len(store.history('us'))==1 and len(store.history('korea'))==1


def test_scheduler_background_execution(monkeypatch):
    import threading
    ran=threading.Event();monkeypatch.setattr(scheduler,'tick',ran.set)
    stop=scheduler.start()
    try:assert ran.wait(5)
    finally:stop.set()


@pytest.mark.parametrize('failure',['feature','inference'])
def test_real_inference_failure_and_no_training(tmp_path,monkeypatch,failure):
    """Use real staged calculators/features and existing weights; force inference to fail."""
    from src.operations import worker
    from src.api import main as api
    import joblib, hashlib
    # Redirecting calculator globals must remain isolated from this test process too.
    import subprocess, sys
    script='''
import json, sys
from pathlib import Path
from src.operations.refresh import legacy, stage_inputs
from src.operations.worker import build
from src.api import main as api
from src.operations.validation import ValidationFailure
import joblib
stage=Path(sys.argv[1]);stage.mkdir()
frames=legacy('us')
stage_inputs('us',stage,frames,[],'legacy-cache','2026-10-14')
class BrokenModel:
    def predict_proba(self,*args,**kwargs):raise RuntimeError('injected inference failure')
joblib.load=lambda *args,**kwargs:BrokenModel()
if sys.argv[2]=='feature':
    from src.features.engineering import FeatureEngineer
    def fail_features(self):raise RuntimeError('injected feature failure')
    FeatureEngineer.generate_features=fail_features
try:build('us',stage)
except RuntimeError as exc:
    assert 'injected '+sys.argv[2]+' failure' in str(exc)
else:raise AssertionError('Inference unexpectedly succeeded')
assert not (stage/'snapshot.json').exists()
'''
    paths=[api.MODELS_DIR/'xgboost_latest.joblib',api.KOREA_MODEL_DIR/'xgboost_10d_latest.joblib']
    before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path/'worker'),failure],capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stderr[-2000:]
    assert before==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]


def test_failed_refresh_retries_even_with_current_lkg(monkeypatch):
    jid=job();store.publish(jid,'us',payload('2026-10-09'))
    with store.database() as db:
        db.execute("INSERT INTO jobs (job_id,market,trigger,expected_date,started_at,status) VALUES ('failed','us','manual','2026-10-09',?,'ERROR')",((datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),))
        db.execute("UPDATE jobs SET started_at=? WHERE job_id=?",((datetime.now(timezone.utc)-timedelta(hours=2)).isoformat(),jid))
    monkeypatch.setattr(scheduler,'expected',lambda *a:('2026-10-09','2026-10-10T08:00:00+00:00'))
    calls=[];monkeypatch.setattr(scheduler,'refresh',lambda market,trigger:calls.append((market,trigger)) or {})
    scheduler.tick()
    assert ('us','scheduled-retry') in calls


def test_publication_requires_matching_market_job():
    jid=job('us')
    with pytest.raises(ValueError,match='same market'):store.publish(jid,'korea',payload())
    assert store.snapshot('korea') is None


def test_treasury_holiday_differs_from_equity_calendar(monkeypatch):
    from src.operations.calendar import series_expected
    assert series_expected('us','DGS10','2026-10-12')=='2026-10-09'
    assert series_expected('us','SPY','2026-10-12')=='2026-10-12'
    jid=job();data=payload('2026-10-09')
    for item in data['input_series']:
        if item['series']!='DGS10':item['latest_observation_date']='2026-10-12'
    store.publish(jid,'us',data)
    monkeypatch.setattr(service,'expected',lambda *a:('2026-10-12','2026-10-13T08:00:00+00:00'))
    result=service.health('us')
    assert result['status']=='CURRENT'
    assert result['input_series'][-1]['expected_observation_date']=='2026-10-09'


@pytest.mark.parametrize('status,body,exception',[(200,b'',TransientProviderError),(429,b'limited',TransientProviderError),(503,b'failure',TransientProviderError),(401,b'denied',ValidationFailure)])
def test_http_failure_classification(monkeypatch,status,body,exception):
    import requests
    response=requests.Response();response.status_code=status;response._content=body
    monkeypatch.setattr('src.operations.providers.requests.get',lambda *a,**kw:response)
    with pytest.raises(exception):Providers.http('https://fixture.invalid')


def test_malformed_fred_schema_is_permanent(monkeypatch):
    from types import SimpleNamespace
    jid=job();provider=Providers(jid,sleep=lambda _:pytest.fail('schema error retried'))
    monkeypatch.setattr(provider,'http',lambda *a,**kw:SimpleNamespace(text='unexpected,column\n1,2\n'))
    with pytest.raises(ValidationFailure):provider.fred('DBAA','2026-10-12')
    assert len(store.history()[0]['attempts'])==1


def test_worker_failure_records_stderr_even_without_calculation_log(monkeypatch, caplog):
    """Import/startup errors and uncaught tracebacks must not become normal-output errors."""
    from types import SimpleNamespace
    monkeypatch.setattr(refresh_module, 'expected', lambda _: ('2026-10-09', '2026-10-12T00:00:00+00:00'))
    monkeypatch.setattr(refresh_module, 'seeds', lambda _: {})
    dates = pd.bdate_range(end='2026-10-09', periods=500)
    class CachedProviders:
        def __init__(self, _): self.counts = {}
        def yahoo(self, name, *args):
            self.counts[name] = 1
            return pd.DataFrame({name: np.arange(500, dtype=float) + 10}, index=dates), store.utcnow()
        fred = yahoo
    monkeypatch.setenv('ECOS_API_KEY', 'worker-test-private-key')
    traceback = 'Traceback (most recent call last):\nFileNotFoundError: required artifact absent worker-test-private-key\n'
    monkeypatch.setattr(refresh_module.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout='Normal progress only', stderr=traceback))
    result = refresh_module.refresh('us', providers_factory=CachedProviders)
    stage = store.root() / 'staging' / result['job_id']
    assert result['status'] == 'ERROR' and not result['snapshot_published']
    assert 'exit_code=1' in result['error_message'] and 'FileNotFoundError' not in result['error_message']
    assert (stage / 'worker.stderr.log').read_text() == traceback.replace('worker-test-private-key', '[REDACTED]')
    assert 'worker-test-private-key' not in caplog.text
    assert 'FileNotFoundError' in (stage / 'worker.diagnostic.log').read_text()
    assert 'CALCULATION' in (stage / 'worker.diagnostic.log').read_text()
    assert (stage / 'worker.stdout.log').read_text() == 'Normal progress only'
    assert 'FileNotFoundError' in caplog.text
    assert store.history()[0]['error_message'] == result['error_message']


@pytest.mark.parametrize('failure', [False, True])
def test_real_korea_worker_without_research_targets(tmp_path, failure):
    """Missing research labels cannot block inference; actual model errors still fail."""
    import subprocess, sys
    script = '''
import hashlib,json,os,sys
from pathlib import Path
from src.operations import refresh,store
from src.config import MODELS_DIR
stage=store.root()/'staging'/'korea-test';stage.mkdir(parents=True)
frames=refresh.legacy('korea')
refresh.stage_inputs('korea',stage,frames,[],'legacy-cache','2026-10-15')
# No processed research target directory exists in this isolated runtime root.
os.environ['MARKET_DATA_ROOT']=str(stage.parent/'missing-research-cache')
from src.api import main as api
api.KOREA_PROCESSED_DIR=Path(os.environ['MARKET_DATA_ROOT'])/'processed/korea'
assert not (api.KOREA_PROCESSED_DIR/'korea_targets.csv').exists()
if sys.argv[1]=='True':
    import joblib
    class BrokenModel:
        def predict_proba(self,*args,**kwargs): raise RuntimeError('injected Korea inference failure')
    joblib.load=lambda *args,**kwargs: BrokenModel()
from src.operations.worker import build
build('korea',stage)
value=json.loads((stage/'snapshot.json').read_text())
assert value['feature_count']==17
assert value['artifact_directory']=='staging/korea-test'
assert value['model_sha256']==hashlib.sha256((api.KOREA_MODEL_DIR/'xgboost_10d_latest.joblib').read_bytes()).hexdigest()
'''
    result = subprocess.run([sys.executable, '-c', script, str(failure)], capture_output=True, text=True, timeout=180)
    if failure:
        assert result.returncode != 0
        assert 'injected Korea inference failure' in result.stderr
        assert not (store.root() / 'staging/korea-test/snapshot.json').exists()
    else:
        assert result.returncode == 0, result.stderr[-2000:]


def test_delayed_snapshot_available_and_public_health_has_no_traceback(monkeypatch):
    monkeypatch.setattr(service, 'expected', lambda *args: ('2026-10-12', '2026-10-13T08:00:00+00:00'))
    jid=job(); value=payload('2026-10-09');value.update(risk_score_10d=11.9,market_stress_index=-1.159)
    store.publish(jid,'us',value)
    with store.database() as db:
        db.execute('UPDATE jobs SET expected_date=? WHERE job_id=?',('2026-10-12',jid))
    current=service.current_payload('us')
    assert current['data_health']['status']=='DELAYED'
    assert current['data_health']['model_available'] and not current['data_health']['is_current']
    assert current['risk_score_10d']==11.9 and current['market_stress_index']==-1.159
    assert 'unavailable' not in current['data_health']['message'].lower()
    with store.database() as db:
        db.execute("UPDATE jobs SET status='ERROR',error_message='Traceback: /internal/path' WHERE job_id=?",(jid,))
    health=service.health('us')
    assert health['status']=='ERROR' and health['model_available']
    assert 'Traceback' not in json.dumps(health) and '/internal/path' not in json.dumps(health)


def test_no_snapshot_unavailable():
    assert not service.health('korea')['model_available']


def test_worker_diagnostic_redacts_credentials(monkeypatch):
    monkeypatch.setenv('ECOS_API_KEY','test-secret-for-redaction')
    assert refresh_module.redact_diagnostic('API=test-secret-for-redaction')=='API=[REDACTED]'


@pytest.mark.parametrize('market,deadline', [
    ('korea', datetime(2026, 10, 14, 12, 30, tzinfo=timezone.utc)),
    ('us', datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)),
])
@pytest.mark.parametrize('offset_seconds', [-1, 0, 1])
def test_refresh_provider_cutoff_respects_publication_deadline(monkeypatch, market, deadline, offset_seconds):
    """Real KRX session enumeration/FRED request bounds follow readiness, not close."""
    _check_refresh_boundary(monkeypatch, market, deadline, offset_seconds)


@pytest.mark.parametrize('offset_seconds', [-1, 0])
def test_missing_krx_new_session_only_fails_when_due(monkeypatch, offset_seconds):
    _check_refresh_boundary(
        monkeypatch, 'korea', datetime(2026, 10, 14, 12, 30, tzinfo=timezone.utc),
        offset_seconds, missing_new_session=True,
    )


def _check_refresh_boundary(monkeypatch, market, deadline, offset_seconds, missing_new_session=False):
    from pathlib import Path
    from types import SimpleNamespace
    from src.operations.calendar import calendar, latest_closed

    now = deadline + timedelta(seconds=offset_seconds)
    due = '2026-10-13' if offset_seconds < 0 else '2026-10-14'
    assert latest_closed(market, now) == '2026-10-14'
    assert expected(market, now)[0] == due
    monkeypatch.setattr(refresh_module, 'expected', lambda m: expected(m, now))
    dates = calendar(market, now.year).sessions_in_range('2024-01-02', '2026-10-13')[-500:]
    dates = dates.tz_localize(None) if dates.tz is not None else dates
    bases = {name: pd.DataFrame({name: np.arange(500, dtype=float) + 10}, index=dates)
             for name in refresh_module.SERIES[market]}
    monkeypatch.setattr(refresh_module, 'seeds', lambda _: bases)
    old = {**payload('2026-10-13'), 'input_series': [
        {'series': n, 'latest_observation_date': '2026-10-13', 'retrieved_at': store.utcnow()}
        for n in bases
    ]}
    sid = store.publish(job(market), market, old)
    requested = []
    monkeypatch.setenv('KRX_API_KEY', 'fixture-boundary-key')

    def observations(name, end):
        result = bases[name].copy()
        if end == '2026-10-14':
            result.loc[pd.Timestamp(end), name] = 510.
        return result

    class BoundaryProviders(Providers):
        def __init__(self, jid):
            super().__init__(jid, sleep=lambda _: None)

        def http(self, url, **kwargs):
            if 'krx.co.kr' in url:
                date = kwargs['params']['basDd']
                name = 'KOSPI200' if 'kospi_dd_trd' in url else 'VKOSPI'
                requested.append((name, pd.Timestamp(date).strftime('%Y-%m-%d')))
                rows = [] if missing_new_session and date == '20261014' else [{
                    'IDX_NM': '코스피 200' if name == 'KOSPI200' else '코스피 200 변동성지수',
                    'BAS_DD': date, 'CLSPRC_IDX': '510',
                }]
                return SimpleNamespace(json=lambda: {'OutBlock_1': rows})
            params = kwargs['params']
            name, end = params['id'], params['coed']
            requested.append((name, end))
            data = observations(name, end)
            # Use the real FRED parser and validation, without network requests.
            return SimpleNamespace(text=data.rename_axis('observation_date').to_csv())

        def yahoo(self, name, end):
            requested.append((name, end))
            return observations(name, end), store.utcnow()

        def ecos(self, name, end):
            requested.append((name, end))
            return observations(name, end), store.utcnow()

    def worker(args, **kwargs):
        stage = Path(args[-1])
        spec = json.loads((stage / 'inputs.json').read_text())
        result = {**payload(spec['common_date']), 'input_series': spec['series'],
                  'artifact_directory': str(stage), 'anomalies': [], 'model_inference_at': store.utcnow()}
        (stage / 'snapshot.json').write_text(json.dumps(result))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(refresh_module.subprocess, 'run', worker)
    report = refresh_module.refresh(market, providers_factory=BoundaryProviders)
    assert report['expected_date'] == report['fetch_through_date'] == due
    assert set(name for name, _ in requested) == set(bases)
    assert max(date for _, date in requested) == due
    if missing_new_session and offset_seconds >= 0:
        assert report['status'] == 'ERROR' and not report['snapshot_published']
        assert {s['series'] for s in report['series'] if s['status'] == 'ERROR'} == {'KOSPI200', 'VKOSPI'}
        assert store.snapshot(market)['snapshot_id'] == sid
    else:
        assert report['status'] == 'SUCCESS' and report['snapshot_published']
        assert report['common_feature_date'] == due
        assert all(s['status'] == 'CURRENT' for s in report['series'])
        assert store.snapshot(market)['observation_date'] == due
