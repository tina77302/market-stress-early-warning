"""Offline deterministic analytics; never reset accounts or contact providers."""
import copy
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pytest
from src.paper import stress_analytics as a
from tests.test_unified_investment import investment_env


def history(market='us', periods=1201):
    dates = pd.bdate_range('2010-01-01', periods=periods)
    prices = pd.Series(100*np.exp(np.arange(periods)*.0002), index=dates)
    return {'scores': pd.Series(10., index=dates), 'benchmark': prices, 'label': 'SPY' if market=='us' else 'KOSPI200', 'sources': {'fixture': 'checksum'}}


def latest(day='2014-08-08'):
    return {'last_updated': day, 'risk_score_10d': 10., 'warning_active': False,
            'model_sha256': 'frozen-fixture', 'data_health': {'is_current': True, 'model_available': True, 'snapshot_id': 'fixture'}}


def investment(holdings=None):
    holdings = holdings or {'us': [], 'korea': []}
    return {'portfolio_value':100000.,'valuation_complete':True,'cash':50000.,'observed_at':'2026-10-15T00:00:00Z',
            'cash_balances':{'USD':50000.,'KRW':0.},'fx':{'rate':1000.},
            'books': {market:{'positions': rows} for market,rows in holdings.items()}}


def record(symbol='AAA', kind='security', market='us', **extra):
    return {'symbol':symbol,'kind':kind,'currency':'USD' if market=='us' else 'KRW', 'sector':'Technology', 'industry':'Semiconductors' if kind=='security' else None,
            'source':'https://example.org/reviewed-provider','reviewed_at':'2026-10-01T00:00:00+00:00','identity_verified':True,
            'return_basis':'split_and_dividend_adjusted_close','prices':history(market)['benchmark'], **extra}


def fixtures(monkeypatch, records):
    monkeypatch.setattr(a, 'load_market', history)
    monkeypatch.setattr(a, 'load_evidence', lambda market:(records.get(market, {}),'reviewed-hash'))


def test_market_regimes_are_separate_and_use_existing_boundaries():
    assert [a.regime('us',v) for v in [29.9,30,50,70]]==['LOW','WATCH','ELEVATED','HIGH']
    assert a.regime('korea',30)=='BELOW WARNING' and a.regime('korea',50)=='WARNING'
    for value in [float('nan'),float('inf'),-1,101]:
        with pytest.raises(ValueError): a.regime('us',value)
    with pytest.raises(ValueError):a.regime('other',30)


def test_ten_sessions_nonoverlap_no_future_leakage_and_no_outcome_selection():
    h=history(periods=104)
    windows=a.selected_events(h['scores'],h['benchmark'].index,h['benchmark'].index[-1],'us','LOW')
    assert len(windows)==10
    assert all(len(s)==11 for _,_,s in windows)
    assert all(windows[i][1] <= windows[i+1][0] for i in range(len(windows)-1))
    assert all(end <= h['benchmark'].index[-1] for _,end,_ in windows)
    trimmed=a.selected_events(h['scores'],h['benchmark'].index,h['benchmark'].index[29],'us','LOW')
    assert len(trimmed)==2
    assert a.selected_events(h['scores'],h['benchmark'].index,h['benchmark'].index[-1],'korea','WARNING')==[]


def test_complete_sessions_required_no_compression_or_forward_fill():
    h=history(periods=31)
    windows=a.selected_events(h['scores'],h['benchmark'].index,h['benchmark'].index[-1],'us','LOW')
    assert len(a.instrument_events(h['benchmark'],windows))==3
    broken=h['benchmark'].drop(h['benchmark'].index[5])
    result=a.instrument_events(broken,windows)
    assert len(result)==2 and result[0]['date']==windows[1][0].date().isoformat()


def test_empirical_statistics_and_insufficient_tails():
    events=[{'return_pct':float(i)} for i in range(-10,10)]
    stats=a.distribution(events)
    assert stats['n']==20 and stats['median_pct']==-.5
    assert stats['q25_pct']==-5.25 and stats['q75_pct']==4.25
    assert stats['negative_frequency']==.5 and stats['dispersion_iqr_pct']==9.5
    assert stats['sample_std_pct']==pytest.approx(np.std(np.arange(-10,10),ddof=1))
    assert stats['downside_q10_pct'] is None
    assert a.distribution(events[:19])['median_pct'] is None
    hundred=a.distribution([{'return_pct':float(i)} for i in range(100)])
    assert hundred['downside_q10_pct']==pytest.approx(9.9)
    with pytest.raises(ValueError):a.distribution([{'return_pct':float('nan')}])


def test_exposures_known_unknown_cash_and_currency():
    inv=investment({'us':[{'symbol':'AAA','market_value':30000.}], 'korea':[{'symbol':'005930.KS','market_value':20000000.}]})
    rows=a.exposures(inv,{'us':{'AAA':record()},'korea':{}})
    assert rows['holdings'][0]['sector']=='Technology'
    assert rows['holdings'][1]['sector'] is None and rows['holdings'][1]['weight']==.2
    assert rows['largest_security_weight']==.3 and rows['cash_weight']==.5
    assert rows['groups']['currency']==[{'label':'KRW','weight':.2},{'label':'USD','weight':.8}]
    assert {'label':'korea:UNKNOWN','weight':.2} in rows['groups']['sector']
    inv['valuation_complete']=False
    assert all(r['weight'] is None for r in a.exposures(inv,{'us':{},'korea':{}})['holdings'])


def test_security_level_current_weights_outlook_reproducible(monkeypatch):
    fixtures(monkeypatch,{'us':{'AAA':record()}})
    inv=investment({'us':[{'symbol':'AAA','market_value':50000.}],'korea':[]})
    current={m:latest() for m in ('us','korea')}
    result=a.report(inv,current)
    assert result==a.report(inv,current)
    assert result['outlook']['status']=='AVAILABLE'
    assert result['sensitivity'][0]['evidence'][0]['level']=='security'
    assert result['outlook']['distribution']['median_pct']==pytest.approx((np.exp(.002)-1)*100*.5)
    assert result['markets']['us']['model_sha256']=='frozen-fixture'
    assert result['markets']['korea']['regime']=='BELOW WARNING'


def test_sector_fallback_explicit_no_benchmark_substitution(monkeypatch):
    short=record(sector_proxy='TECH');short['prices']=short['prices'].iloc[-5:]
    fixtures(monkeypatch,{'us':{'AAA':short,'TECH':record('TECH','sector')}})
    inv=investment({'us':[{'symbol':'AAA','market_value':50000.}],'korea':[]})
    result=a.report(inv,{'us':latest()})
    assert result['sensitivity'][0]['evidence'][0]['level']=='sector_proxy'
    assert result['outlook']['status']=='AVAILABLE'
    fixtures(monkeypatch,{})
    missing=a.report(inv,{'us':latest()})
    assert missing['markets']['us']['benchmark']['status']=='AVAILABLE'
    assert missing['outlook']['distribution'] is None
    assert missing['sensitivity'][0]['evidence'][0]['level']=='unavailable'


def test_joint_dates_not_marginal_quantiles_and_missing_holding_blocks(monkeypatch):
    first=record(); second=record('BBB');second['prices']=second['prices'].iloc[600:]
    fixtures(monkeypatch,{'us':{'AAA':first,'BBB':second}})
    inv=investment({'us':[{'symbol':'AAA','market_value':30000.},{'symbol':'BBB','market_value':20000.}],'korea':[]})
    result=a.report(inv,{'us':latest()})
    d=result['outlook']['distribution']; assert d and d['n'] < result['markets']['us']['instruments']['AAA']['n']
    fixtures(monkeypatch,{'us':{'AAA':first}})
    assert a.report(inv,{'us':latest()})['outlook']['distribution'] is None


def test_mixed_markets_never_pool_regimes_or_quantiles(monkeypatch):
    fixtures(monkeypatch,{'us':{'AAA':record()},'korea':{'005930.KS':record('005930.KS',market='korea')}})
    inv=investment({'us':[{'symbol':'AAA','market_value':30000.}],'korea':[{'symbol':'005930.KS','market_value':20000000.}]})
    result=a.report(inv,{m:latest() for m in ('us','korea')})
    assert all(s['status']=='AVAILABLE' for s in result['sensitivity'])
    assert result['outlook']['distribution'] is None and result['outlook']['status']=='SEPARATE_MARKET_EVIDENCE_REQUIRED'


def test_korean_warning_boolean_not_rounded_us_band(monkeypatch):
    fixtures(monkeypatch,{})
    current=latest();current.update(risk_score_10d=50.,warning_active=False)
    result,_=a.market_analysis('korea',current)
    assert result['regime']=='BELOW WARNING'


def test_stale_or_invalid_history_is_independent_per_market(monkeypatch):
    fixtures(monkeypatch,{})
    stale=latest();stale['data_health']['is_current']=False
    result=a.report(investment(),{'us':stale,'korea':latest()})
    assert result['markets']['us']['status']=='UNAVAILABLE'
    assert result['markets']['korea']['status']=='AVAILABLE'
    assert result['outlook']['status']=='NO_HOLDINGS'
    def load(market):
        if market=='us':raise ValueError('bad history')
        return history(market)
    monkeypatch.setattr(a,'load_market',load)
    result=a.report(investment(),{m:latest() for m in ('us','korea')})
    assert result['markets']['korea']['status']=='AVAILABLE' and result['markets']['us']['status']=='UNAVAILABLE'


def serializable_record(**kwargs):
    item=record(**kwargs);prices=item.pop('prices')
    item['prices']=[{'Date':d.date().isoformat(),'Close':float(v)} for d,v in prices.items()]
    return item


@pytest.mark.parametrize('mutation',[
    lambda x:x.update(currency='KRW'),lambda x:x.update(identity_verified=False),lambda x:x.update(return_basis='unadjusted'),
    lambda x:x.update(source=''),lambda x:x['prices'].append(x['prices'][0]),lambda x:x['prices'][0].update(Close=-1),
    lambda x:x.update(sector_proxy='MISSING')])
def test_evidence_validation_rejects_invalid_or_unverified(mutation):
    item=serializable_record();mutation(item)
    with pytest.raises((ValueError,KeyError)):
        a.parse_evidence(json.dumps({'schema_version':1,'market':'us','instruments':[item]}).encode(),'us')


def test_atomic_import_lkg_and_identity(tmp_path,monkeypatch):
    from src.admin import import_stress_evidence as importer
    master=tmp_path/'master.sqlite3'
    with sqlite3.connect(master) as db:
        db.execute('CREATE TABLE securities (market TEXT,symbol TEXT,currency TEXT,active INTEGER,security_type TEXT)')
        db.execute("INSERT INTO securities VALUES ('us','AAA','USD',1,'Stock')")
    monkeypatch.setattr(importer,'master_path',lambda:master)
    monkeypatch.setattr(importer,'DATA_DIR',tmp_path)
    monkeypatch.setattr(a,'DATA_DIR',tmp_path)
    bundle={'schema_version':1,'market':'us','instruments':[serializable_record()]}
    source=tmp_path/'input.json';source.write_text(json.dumps(bundle))
    assert importer.publish(source,'us')['status']=='PUBLISHED'
    records,digest=a.load_evidence('us');assert records['AAA']['sector']=='Technology'
    bundle['instruments'][0]['prices'][0]['Close']=0
    source.write_text(json.dumps(bundle))
    with pytest.raises(ValueError):importer.publish(source,'us')
    assert a.load_evidence('us')[1]==digest
    bundle['instruments'][0]['symbol']='UNLISTED';source.write_text(json.dumps(bundle))
    with pytest.raises(ValueError):importer.publish(source,'us')
    assert a.load_evidence('us')[1]==digest


def test_endpoint_auth_owner_and_role_parity(investment_env,monkeypatch):
    pairs,_=investment_env
    fixtures(monkeypatch,{})
    from src.operations import service
    monkeypatch.setattr(service,'current_payload',lambda market:latest())
    calls=[]
    from src.paper import investment as inv
    original=inv.summary
    def tracked(uid):
        calls.append(uid);return original(uid)
    monkeypatch.setattr(inv,'summary',tracked)
    responses=[client.get('/api/paper/stress-analytics') for client,_ in pairs]
    assert all(r.status_code==200 for r in responses)
    assert calls==[1,2]
    assert responses[0].json()['exposure']==responses[1].json()['exposure']
    assert responses[0].json()['markets']==responses[1].json()['markets']
    assert responses[0].headers['cache-control']=='no-store'
    client=pairs[0][0];client.cookies.clear()
    assert client.get('/api/paper/stress-analytics').status_code==401


def test_classification_only_survives_stale_stress(monkeypatch):
    item=record();item['prices']=item['prices'].iloc[:0]
    fixtures(monkeypatch,{'us':{'AAA':item}})
    current=latest();current['data_health']['is_current']=False
    result=a.report(investment({'us':[{'symbol':'AAA','market_value':50000.}],'korea':[]}),{'us':current})
    assert result['exposure']['holdings'][0]['sector']=='Technology'
    assert result['outlook']['distribution'] is None
    encoded=serializable_record();encoded['prices']=[]
    records,_=a.parse_evidence(json.dumps({'schema_version':1,'market':'us','instruments':[encoded]}).encode(),'us')
    assert records['AAA']['prices'].empty


def test_reader_hashes_exact_bytes_and_actual_repository_histories():
    # Offline production inputs: smoke-test both existing calendar/OOS formats.
    for market in ('us','korea'):
        try:
            data=a.load_market(market)
        except FileNotFoundError:
            pytest.skip('Historical artifacts not installed in this environment')
        assert len(data['scores'])>100 and len(data['benchmark'])>100
        assert len(data['sources'])==2 and all(len(digest)==64 for digest in data['sources'].values())


def test_incomplete_joint_sample_withholds_portfolio_statistics(monkeypatch):
    first=record();second=record('BBB')
    # Each individually supports central statistics, but their joint sample does not.
    first['prices']=first['prices'].iloc[:650]
    second['prices']=second['prices'].iloc[600:]
    fixtures(monkeypatch,{'us':{'AAA':first,'BBB':second}})
    inv=investment({'us':[{'symbol':'AAA','market_value':30000.},{'symbol':'BBB','market_value':20000.}],'korea':[]})
    result=a.report(inv,{'us':latest()})
    assert all(result['markets']['us']['instruments'][s]['n']>=20 for s in ['AAA','BBB'])
    stats=result['outlook']['distribution']
    assert stats['status']=='INSUFFICIENT_SAMPLE' and stats['n']<20 and stats['median_pct'] is None


def test_proxy_cannot_cross_sector_or_market(monkeypatch):
    short=record(sector_proxy='OTHER');short['prices']=short['prices'].iloc[:5]
    fixtures(monkeypatch,{'us':{'AAA':short,'OTHER':record('OTHER','sector',sector='Energy')}})
    inv=investment({'us':[{'symbol':'AAA','market_value':50000.}],'korea':[]})
    assert a.report(inv,{'us':latest()})['outlook']['distribution'] is None
    fixtures(monkeypatch,{'us':{'AAA':short},'korea':{'OTHER':record('OTHER','sector',market='korea')}})
    assert a.report(inv,{m:latest() for m in ['us','korea']})['outlook']['distribution'] is None


def test_listing_equity_cannot_be_imported_as_sector_etf(tmp_path,monkeypatch):
    from src.admin import import_stress_evidence as importer
    master=tmp_path/'master.sqlite3'
    with sqlite3.connect(master) as db:
        db.execute('CREATE TABLE securities (market TEXT,symbol TEXT,currency TEXT,active INTEGER,security_type TEXT)')
        db.execute("INSERT INTO securities VALUES ('us','AAA','USD',1,'Stock')")
    monkeypatch.setattr(importer,'master_path',lambda:master);monkeypatch.setattr(importer,'DATA_DIR',tmp_path)
    source=tmp_path/'input.json'
    source.write_text(json.dumps({'schema_version':1,'market':'us','instruments':[serializable_record(kind='sector')]}))
    with pytest.raises(ValueError,match='ETF'):importer.publish(source,'us')
    assert not (tmp_path/'paper/stress-evidence/us.json').exists()


def test_held_sector_etf_uses_its_own_security_return_history(monkeypatch):
    fixtures(monkeypatch,{'us':{'TECH':record('TECH','sector')}})
    inv=investment({'us':[{'symbol':'TECH','market_value':50000.}],'korea':[]})
    result=a.report(inv,{'us':latest()})
    assert result['outlook']['status']=='AVAILABLE'
    assert result['sensitivity'][0]['evidence'][0]['level']=='security'


def test_endpoint_held_portfolio_end_to_end(investment_env,monkeypatch):
    from tests.test_unified_investment import quote,reviewed,submit
    pairs,_=investment_env
    fixtures(monkeypatch,{'us':{'AAPL':record('AAPL')}})
    from src.operations import service
    monkeypatch.setattr(service,'current_payload',lambda market:latest('2026-10-14'))
    pair=pairs[1]
    assert submit(pair,reviewed(pair[0],quote(pair[0],'us','AAPL'))).status_code==201
    response=pair[0].get('/api/paper/stress-analytics?user_id=1')
    assert response.status_code==200
    data=response.json()
    assert data['exposure']['holdings'][0]['symbol']=='AAPL'
    assert data['outlook']['status']=='AVAILABLE'
    assert data['outlook']['distribution']['n']>=20
    # Query parameters cannot select the other account's holdings.
    assert pairs[0][0].get('/api/paper/stress-analytics?user_id=2').json()['outlook']['status']=='NO_HOLDINGS'


@pytest.mark.parametrize('field,value',[('sector',['Technology']),('industry',23),('source',123),('prices',{}),('identity_verified',1)])
def test_metadata_types_cannot_be_misrepresented_as_verified(field,value):
    item=serializable_record();item[field]=value
    with pytest.raises(ValueError):
        a.parse_evidence(json.dumps({'schema_version':1,'market':'us','instruments':[item]}).encode(),'us')
