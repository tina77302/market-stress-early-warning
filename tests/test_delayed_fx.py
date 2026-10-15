"""exchangerate.dev delayed-feed policy and immutable accounting, entirely offline."""
import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from src.paper import fx,fx_exchange_rate as provider
from src.paper.store import database
from tests.test_execution_fx import env,trade,summary
from tests.test_unified_investment import investment_env,quote,reviewed,submit


def response(age=930):
    now=datetime.now(timezone.utc)-timedelta(seconds=1)
    result=Mock(status_code=200,headers={'X-Price-Delay-Seconds':'900'})
    result.json.return_value={'result':'success','base':'USD','rates':{'KRW':'1350.123456789123456789'},
        'effective_at':{'KRW':(now-timedelta(seconds=age)).isoformat()}, 'timestamp':now.isoformat(),
        'data_updated_at':now.isoformat(),'sources':{'KRW':'live'},'market_session':'open','stale':{'KRW':False}}
    return result


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('PAPER_FX_PRIMARY_PROVIDER','exchangerate_dev')
    monkeypatch.setenv('EXCHANGERATE_API_KEY','fixture-key-not-for-output')
    monkeypatch.setattr(fx,'_primary_retry_after',0)
    item=response()
    monkeypatch.setattr(provider.requests,'get',lambda *a,**k:item)
    return item


def test_default_and_explicit_fred_only_configuration(monkeypatch):
    monkeypatch.delenv('PAPER_FX_PRIMARY_PROVIDER',raising=False)
    assert fx.preferred_provider()=='exchangerate_dev'
    monkeypatch.setenv('PAPER_FX_PRIMARY_PROVIDER','')
    assert fx.preferred_provider()==''


def test_delayed_rate_uses_actual_observation_not_response_time(enabled):
    row=provider.fetch_observation();assert fx.validate(row)==Decimal('1350.123456789123456789')
    public=fx.public(row)
    assert public['freshness_status']=='DELAYED' and public['selection_role']=='primary'
    assert public['kind']=='delayed_observation' and public['feed_delay_seconds']==900
    assert public['max_observation_age_seconds']==1800 and public['max_retrieval_age_seconds']==900
    assert row['observation_timestamp']!=row['response_timestamp']
    assert row['observation_timestamp']==provider.timestamp(enabled.json.return_value['effective_at']['KRW']).isoformat()


@pytest.mark.parametrize('change',[
    lambda d:d['stale'].update(KRW=True),lambda d:d['stale'].update(KRW=0),
    lambda d:d.update(base='KRW'),lambda d:d['rates'].update(KRW='NaN'),
    lambda d:d['rates'].update(KRW='-1'),lambda d:d['rates'].update(KRW='Infinity'),
    lambda d:d['sources'].update(KRW='ecb_daily'),lambda d:d['sources'].update(KRW='market_daily'),
    lambda d:d['effective_at'].update(KRW='2026-10-15T00:00:00'),
    lambda d:d['effective_at'].update(KRW=(datetime.now(timezone.utc)-timedelta(minutes=31)).isoformat()),
    lambda d:d['effective_at'].update(KRW=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()),
    lambda d:d.update(market_session='unknown'),lambda d:d.update(timestamp='bad')])
def test_bad_metadata_or_independently_old_observation_rejected(enabled,change):
    change(enabled.json.return_value)
    with pytest.raises(HTTPException):provider.fetch_observation()


def test_cached_ages_independently_checked(enabled):
    row=provider.fetch_observation()
    bad={**row,'observation_timestamp':(datetime.now(timezone.utc)-timedelta(minutes=31)).isoformat()}
    with pytest.raises(HTTPException):fx.validate(bad)
    old=datetime.now(timezone.utc)-timedelta(minutes=16)
    bad={**row,'retrieved_at':old.isoformat(),'response_timestamp':old.isoformat(),'data_updated_at':old.isoformat(),
         'observation_timestamp':(old-timedelta(minutes=10)).isoformat()}
    with pytest.raises(HTTPException):fx.validate(bad)
    for key in ['provider_stale','observation_timestamp','response_timestamp','data_updated_at']:
        bad=dict(row);bad.pop(key)
        with pytest.raises(HTTPException):fx.validate(bad)


def test_closed_market_does_not_bypass_age_validation(enabled):
    enabled.json.return_value['market_session']='weekend'
    enabled.json.return_value['effective_at']['KRW']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    with pytest.raises(HTTPException):provider.fetch_observation()


def test_key_in_header_only_and_redirects_disabled(monkeypatch,enabled):
    def get(url,**options):
        assert 'fixture-key' not in url and 'fixture-key' not in str(options['params'])
        assert options['headers']['Authorization']=='Bearer fixture-key-not-for-output'
        assert options['allow_redirects'] is False
        return enabled
    monkeypatch.setattr(provider.requests,'get',get)
    assert provider.fetch_observation()['source']==provider.SOURCE
    def fail(*args,**kwargs):raise RuntimeError('fixture-key-not-for-output')
    monkeypatch.setattr(provider.requests,'get',fail)
    with pytest.raises(HTTPException) as error:provider.fetch_observation()
    assert 'fixture-key' not in str(error.value.detail)


@pytest.mark.parametrize('header',[None,'0','60','invalid'])
def test_free_feed_delay_header_required(enabled,header):
    enabled.headers={'X-Price-Delay-Seconds':header}
    with pytest.raises(HTTPException):provider.fetch_observation()


def test_persistence_cache_quota_and_immutable_context(env,monkeypatch,enabled):
    calls=[]
    monkeypatch.setattr(provider.requests,'get',lambda *a,**k:(calls.append(1) or enabled))
    first=fx.latest();again=fx.latest()
    assert first==again and len(calls)==1
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(lambda _:fx.latest(),range(8)))
    assert len(calls)==1 and all(r['id']==first['id'] for r in rows)
    with database() as db:
        saved=fx.enrich(db,db.execute('SELECT * FROM paper_fx_rates WHERE id=?',(first['id'],)).fetchone())
        assert saved==first and saved['provider_stale'] is False
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE paper_fx_provider_context SET detail_json='{}' WHERE rate_id=?",(first['id'],))


def test_provider_error_falls_back_and_respects_retry_after(env,monkeypatch,enabled):
    calls=[];enabled.status_code=429;enabled.headers['Retry-After']='3600'
    monkeypatch.setattr(provider.requests,'get',lambda *a,**k:(calls.append(1) or enabled))
    now=fx.time.monotonic()
    first=fx.latest();assert first['source']==fx.SOURCE
    assert fx.public(first)['selection_role']=='fallback'
    assert fx._primary_retry_after>=now+3600
    assert fx.latest()['source']==fx.SOURCE and len(calls)==1


def test_invalid_preferred_and_invalid_fred_fail_closed(env,monkeypatch,enabled):
    enabled.json.return_value['stale']['KRW']=True
    original=fx.validate
    def validate(row):
        if row['source']==fx.SOURCE:raise HTTPException(503,'Daily observation too old')
        return original(row)
    monkeypatch.setattr(fx,'validate',validate)
    with pytest.raises(HTTPException):fx.latest()


def test_missing_key_falls_back_without_provider_call(env,monkeypatch,enabled):
    monkeypatch.delenv('EXCHANGERATE_API_KEY')
    monkeypatch.setattr(provider.requests,'get',lambda *a,**k:pytest.fail('No key: no network'))
    assert fx.latest()['source']==fx.SOURCE


def test_execution_history_survives_source_change_and_revaluation(env,monkeypatch,enabled):
    pair=env[0][1]
    first=trade(pair)
    frozen=copy.deepcopy(first['execution_details'])
    assert frozen['fx']['source']==provider.SOURCE and frozen['fx']['freshness_status']=='DELAYED'
    assert frozen['fx']['observation_timestamp']!=frozen['fx']['response_timestamp']
    # Switching adapters changes current valuation only, never recorded execution FX.
    monkeypatch.setenv('PAPER_FX_PRIMARY_PROVIDER','')
    data,attribution=summary(pair)
    assert data['fx']['source']==fx.SOURCE and attribution['available']
    orders=pair[0].get('/api/paper/orders?market=korea').json()['data']
    assert orders[0]['execution_details']==frozen
    with database() as db:
        assert json.loads(db.execute('SELECT detail_json FROM paper_order_costs').fetchone()[0])==frozen


def test_age_boundaries_are_deterministic(monkeypatch):
    fixed=datetime(2026,10,15,12,30,tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return fixed
    monkeypatch.setattr(fx,'datetime',Clock)
    data=response().json.return_value
    data.update(timestamp=fixed.isoformat(),data_updated_at=fixed.isoformat())
    data['effective_at']['KRW']=(fixed-timedelta(seconds=1800)).isoformat()
    row=provider.parse(data,fixed);fx.validate(row)
    row['observation_timestamp']=(fixed-timedelta(seconds=1800,microseconds=1)).isoformat()
    with pytest.raises(HTTPException):fx.validate(row)
    retrieved=fixed-timedelta(seconds=900)
    data.update(timestamp=retrieved.isoformat(),data_updated_at=retrieved.isoformat())
    data['effective_at']['KRW']=(fixed-timedelta(seconds=1700)).isoformat()
    row=provider.parse(data,retrieved);fx.validate(row)
    row['retrieved_at']=(retrieved-timedelta(microseconds=1)).isoformat()
    row['response_timestamp']=row['retrieved_at'];row['data_updated_at']=row['retrieved_at']
    with pytest.raises(HTTPException):fx.validate(row)


def test_observation_aging_out_does_not_accelerate_upstream_refresh(env,monkeypatch,enabled):
    fixed=datetime.now(timezone.utc)
    data=enabled.json.return_value
    data.update(timestamp=fixed.isoformat(),data_updated_at=fixed.isoformat())
    data['effective_at']['KRW']=(fixed-timedelta(seconds=1799)).isoformat()
    row=provider.parse(data,fixed);calls=[]
    monkeypatch.setattr(provider,'fetch_observation',lambda:(calls.append(1) or row))
    assert fx.latest()['source']==provider.SOURCE
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return fixed+timedelta(seconds=2)
    monkeypatch.setattr(fx,'datetime',Clock)
    assert fx.latest()['source']==fx.SOURCE
    assert fx.latest()['source']==fx.SOURCE
    assert len(calls)==1
