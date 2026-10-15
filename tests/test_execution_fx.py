"""Deterministic economic attribution from immutable FX/average acquisition bases."""
import json
import sqlite3
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from fastapi import HTTPException
from src.paper import fx,costs,fx_primary
from src.paper.store import database
from tests.test_unified_investment import investment_env,quote,reviewed,submit


@pytest.fixture
def env(investment_env,monkeypatch):
    monkeypatch.setattr(costs,'trade_date',lambda market:'2026-10-15')
    return investment_env


def reference(monkeypatch,rate):
    row={'id':str(uuid4()),'rate':str(rate),'source':fx.SOURCE,'observation_date':datetime.now(timezone.utc).date().isoformat(),'retrieved_at':datetime.now(timezone.utc).isoformat()}
    with database() as db:
        db.execute('INSERT INTO paper_fx_rates VALUES (?,?,?,?,?)',tuple(row[k] for k in ('id','rate','observation_date','retrieved_at','source')));db.commit()
    monkeypatch.setattr(fx,'latest',lambda:row)
    return row


def trade(pair,side='BUY',quantity=10):
    result=submit(pair,reviewed(pair[0],quote(pair[0]),side,quantity))
    assert result.status_code==201,result.text
    return result.json()


def summary(pair):
    result=pair[0].get('/api/paper/investment');assert result.status_code==200,result.text
    data=result.json();a=data['fx_attribution'];assert a['available'],a
    assert a['native_investment_effect_usd']+a['fx_translation_effect_usd']-a['trading_costs_usd']-a['fx_conversion_costs_usd']+a['rounding_residual_usd']==pytest.approx(data['total_pnl'])
    assert a['reconciled_total_usd_pnl']==data['total_pnl']
    return data,a


@pytest.mark.parametrize('price,rate,native,translation,total',[(60000,2000,50,-250,-200),(40000,500,-200,500,300),(60000,500,200,500,700),(40000,2000,-50,-250,-300)])
def test_stock_fx_direction_combinations(env,monkeypatch,price,rate,native,translation,total):
    pairs,marks=env;pair=pairs[1];reference(monkeypatch,1000);filled=trade(pair)
    recorded=filled['execution_details'];assert recorded['fx']['rate_exact']=='1000'
    assert recorded['fx']['source']==fx.SOURCE and recorded['fx']['status']=='AVAILABLE'
    assert recorded['fx']['observation_timestamp'] is None
    assert recorded['fx']['observation_time_precision']=='date'
    marks['korea']=price;reference(monkeypatch,rate)
    data,a=summary(pair)
    assert a['native_investment_effect_usd']==native and a['fx_translation_effect_usd']==translation
    assert data['total_pnl']==total
    assert a['krw_exposure_usd']==10*price/rate
    assert a['krw_exposure_pct']==pytest.approx(10*price/rate/data['portfolio_value']*100)
    history=pair[0].get('/api/paper/orders',params={'market':'korea'}).json()['data'][0]
    assert history['execution_details']==recorded
    assert history['execution_details']['execution_attribution']['gross_usd']=='500'


def test_multiple_acquisitions_partial_sale_and_cash_fx(env,monkeypatch):
    pair=env[0][0];reference(monkeypatch,1000);first=trade(pair)
    reference(monkeypatch,2000);second=trade(pair)
    _,a=summary(pair);p=a['positions'][0]
    assert p['average_acquisition_fx']==pytest.approx(1000000/750)
    assert p['average_purchase_price']==50000
    assert p['fx_effect_usd']==-250
    env[1]['korea']=60000
    sale=trade(pair,'SELL',10)['execution_details']['execution_attribution']
    assert sale['purchase_native_basis']=='500000.0'
    assert float(sale['purchase_usd_basis'])==375
    assert float(sale['purchase_fx_basis'])==pytest.approx(1000000/750)
    assert float(sale['native_realized_stock_pnl'])==100000
    assert float(sale['native_effect_usd'])==50
    assert float(sale['fx_effect_usd'])==-125
    assert float(sale['net_realized_usd'])==-75
    assert sale['execution_fx']['rate_exact']=='2000'
    data,a=summary(pair);assert data['cash_balances']['KRW']==600000 and data['total_pnl']==-150
    reference(monkeypatch,1000)
    data,a=summary(pair);assert a['krw_cash_fx_unrealized_usd']==300 and data['total_pnl']==450
    # Spending retained KRW cash still records the current trade FX without a conversion.
    buy=trade(pair,quantity=1)['execution_details']
    assert buy['from_currency'] is None and buy['fx']['rate_exact']=='1000'
    summary(pair)
    history=pair[0].get('/api/paper/orders',params={'market':'korea'}).json()['data']
    old={row['id']:row for row in history}
    assert old[first['id']]['execution_details']==first['execution_details']
    assert old[second['id']]['execution_details']==second['execution_details']


def test_fees_spread_and_partial_sell_reconcile(env,monkeypatch):
    monkeypatch.delenv('PAPER_COST_CONFIG_PATH',raising=False)
    pair=env[0][1];reference(monkeypatch,1000);trade(pair)
    _,a=summary(pair)
    assert a['trading_costs_usd']==.075
    assert a['fx_conversion_costs_usd']==.501
    assert a['reconciled_total_usd_pnl']==-.58
    reference(monkeypatch,1300);env[1]['korea']=55000
    sold=trade(pair,'SELL',3)['execution_details']['execution_attribution']
    assert float(sold['native_effect_usd'])+float(sold['fx_effect_usd'])-float(sold['allocated_purchase_fees_usd'])-float(sold['fees_usd'])==pytest.approx(float(sold['net_realized_usd']))
    summary(pair)
    reference(monkeypatch,900);summary(pair)


def test_sell_requires_valid_fx_and_history_cannot_update(env,monkeypatch):
    pair=env[0][0];reference(monkeypatch,1000);body=reviewed(pair[0],quote(pair[0]));assert submit(pair,body).status_code==201
    with database() as db:
        before=[tuple(r) for r in db.execute('SELECT * FROM paper_order_costs')]
        with pytest.raises(sqlite3.IntegrityError,match='immutable'):db.execute("UPDATE paper_order_costs SET detail_json='{}'")
        with pytest.raises(sqlite3.IntegrityError,match='immutable'):db.execute("UPDATE paper_fx_rates SET rate='2000'")
    def unavailable():raise HTTPException(503,'FX unavailable')
    monkeypatch.setattr(fx,'latest',unavailable)
    q=quote(pair[0]);response=pair[0].get('/api/paper/settlement',params={'quote_id':q['id'],'side':'SELL','quantity':1})
    assert response.status_code==503
    # Accepted retries retain their historical snapshot even during an FX outage.
    assert submit(pair,body).status_code==201
    with database() as db:assert [tuple(r) for r in db.execute('SELECT * FROM paper_order_costs')]==before


def test_missing_history_is_unavailable_not_invented(env,monkeypatch):
    pair=env[0][0];reference(monkeypatch,1000);trade(pair)
    with database() as db:db.execute('DELETE FROM paper_order_costs');db.commit()
    a=pair[0].get('/api/paper/investment').json()['fx_attribution']
    assert not a['available'] and a['positions']==[]


def test_primary_validation_fallback_and_timestamp_immutability(env,monkeypatch):
    monkeypatch.setenv('PAPER_FX_PRIMARY_PROVIDER','twelve_data');monkeypatch.setenv('PAPER_FX_PRIMARY_LICENSE_CONFIRMED','true')
    monkeypatch.setattr(fx,'_primary_retry_after',0)
    now=datetime.now(timezone.utc)
    item={'id':str(uuid4()),'rate':'1400.25','source':fx_primary.SOURCE,'observation_date':now.date().isoformat(),'observation_timestamp':now.isoformat(),'retrieved_at':now.isoformat()}
    monkeypatch.setattr(fx_primary,'fetch_observation',lambda:item)
    primary=fx.latest();assert primary['source']==fx_primary.SOURCE
    assert fx.public(primary)['observation_timestamp']==now.isoformat()
    q=quote(env[0][0][0]);p=env[0][0][0].get('/api/paper/settlement',params={'quote_id':q['id'],'side':'BUY','quantity':1}).json()
    assert p['fx']['observation_timestamp']==now.isoformat()
    def failure():raise HTTPException(503,'Provider unavailable')
    monkeypatch.setattr(fx_primary,'fetch_observation',failure)
    # Advance validation time by supplying a stale candidate, not mutating stored evidence.
    stale={**item,'observation_timestamp':(now-timedelta(minutes=10)).isoformat()}
    with pytest.raises(HTTPException):fx.validate(stale)
    monkeypatch.setenv('PAPER_FX_PRIMARY_LICENSE_CONFIRMED','false')
    fallback=fx.latest();assert fallback['source']==fx.SOURCE
    assert fx.public(fallback)['selection_role']=='fallback'
    with database() as db:
        assert db.execute('SELECT observation_timestamp FROM paper_fx_metadata').fetchone()[0]==now.isoformat()


def test_primary_no_key_or_license_never_contacts_provider(monkeypatch):
    monkeypatch.delenv('PAPER_FX_PRIMARY_LICENSE_CONFIRMED',raising=False)
    monkeypatch.setattr(fx_primary.requests,'get',lambda *a,**k:pytest.fail('Unlicensed provider request'))
    with pytest.raises(HTTPException):fx_primary.fetch_observation()


def test_primary_failure_visible_fallback_and_both_sources_invalid(env,monkeypatch):
    monkeypatch.setenv('PAPER_FX_PRIMARY_PROVIDER','twelve_data')
    monkeypatch.setenv('PAPER_FX_PRIMARY_LICENSE_CONFIRMED','true')
    monkeypatch.setattr(fx,'_primary_retry_after',0)
    def failure():raise HTTPException(503,'Provider unavailable')
    monkeypatch.setattr(fx_primary,'fetch_observation',failure)
    row=fx.latest();assert row['source']==fx.SOURCE and row['fallback_reason']
    assert fx.public(row)['selection_role']=='fallback'
    original=fx.validate
    def invalid_daily(row):
        if row['source']==fx.SOURCE:raise HTTPException(503,'Daily source stale')
        return original(row)
    monkeypatch.setattr(fx,'validate',invalid_daily)
    monkeypatch.setattr(fx,'fetch_observation',failure)
    with pytest.raises(HTTPException):fx.latest()


def test_reverse_conversion_realizes_cash_fx_once(env,monkeypatch):
    pair=env[0][0];reference(monkeypatch,1000);trade(pair)
    env[1]['korea']=60000;trade(pair,'SELL')
    # USD is 99,500 and KRW is 600,000. A sufficiently large US BUY uses KRW.
    reference(monkeypatch,500);env[1]['us']=10000000 # $100,000 completed-close fixture
    q=quote(pair[0],'us','AAPL');response=submit(pair,reviewed(pair[0],q,quantity=1))
    assert response.status_code==201,response.text
    data,a=summary(pair)
    assert data['cash_balances']['KRW']==350000
    assert data['total_pnl']==700
    assert a['native_investment_effect_usd']==100
    assert a['fx_translation_effect_usd']==600


def test_primary_adapter_identity_and_secret_redaction(monkeypatch):
    from unittest.mock import Mock
    from decimal import Decimal
    monkeypatch.setenv('PAPER_FX_PRIMARY_PROVIDER','twelve_data')
    monkeypatch.setenv('PAPER_FX_PRIMARY_LICENSE_CONFIRMED','true')
    monkeypatch.setenv('TWELVE_DATA_API_KEY','test-key-not-for-logs')
    reply=Mock();reply.json.return_value={'symbol':'USD/KRW','rate':Decimal('1399.123456789123456789'),'timestamp':int(datetime.now(timezone.utc).timestamp())}
    monkeypatch.setattr(fx_primary.requests,'get',lambda *a,**k:reply)
    row=fx_primary.fetch_observation();assert row['rate']=='1399.123456789123456789';fx.validate(row)
    reply.json.return_value={'symbol':'KRW/USD','rate':'0.0007','timestamp':0}
    with pytest.raises(HTTPException) as error:fx_primary.fetch_observation()
    assert 'test-key' not in str(error.value.detail)
    def fail(*args,**kwargs):raise RuntimeError('https://invalid/?apikey=test-key-not-for-logs')
    monkeypatch.setattr(fx_primary.requests,'get',fail)
    with pytest.raises(HTTPException) as error:fx_primary.fetch_observation()
    assert 'apikey' not in str(error.value.detail) and 'test-key' not in str(error.value.detail)


def test_preview_explicit_usd_debit_and_total(env,monkeypatch):
    monkeypatch.delenv('PAPER_COST_CONFIG_PATH',raising=False)
    pair=env[0][0];reference(monkeypatch,1000);q=quote(pair[0])
    data=pair[0].get('/api/paper/settlement',params={'quote_id':q['id'],'side':'BUY','quantity':10}).json()
    assert data['actual_usd_conversion_debit']==500.58
    assert data['estimated_total_usd']==500.58
    assert data['costs']['commission_minor']==75
