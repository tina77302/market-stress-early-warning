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
