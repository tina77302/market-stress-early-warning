"""Listing sources and provider boundaries are deterministic and offline."""
import io
import secrets
import sqlite3
import time
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.paper import prices, security_sources as sources, symbol_master as master
from src.paper.accounts import provision_username_account
from src.paper.router import router
from src.paper.store import database

YAHOO_LOOKUP = master.yahoo_candidates


def nasdaq_bytes(rows, other=False):
    footer = datetime.now(ZoneInfo('America/New_York')).strftime('%m%d%Y%H:%M')
    header = 'ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol' if other else 'Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares'
    return ('\n'.join([header,*rows,'File Creation Time: '+footer+'|||||||'])+'\n').encode()


def kis_bytes(rows,board='kospi'):
    size,halt,liquidation,preferred=(227,60,61,158) if board=='kospi' else (221,55,56,153)
    lines=[]
    for ticker,name,kind,active,pref in rows:
        tail=list(' '*size);tail[:2]=kind;tail[halt]='N' if active else 'Y';tail[liquidation]='N';tail[preferred]=pref
        lines.append(ticker.ljust(9)+'KR7'+ticker+'003'+name.ljust(40)+''.join(tail)+'\n')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:archive.writestr(board+'_code.mst',''.join(lines).encode('cp949'))
    return output.getvalue()


@pytest.mark.parametrize('query,ticker',[
    ('NVDA','NVDA'),('nvd','NVDA'),('NVIDIA','NVDA'),('nvid','NVDA'),
    ('palantir','PLTR'),('PLTR','PLTR'),('VOO','VOO'),
    ('005930','005930'),('삼성전자','005930'),('삼성','005930'),
    ('035420','035420'),('카카오','035720'),('035900','035900'),('KODEX','069500'),
])
def test_search_queries(query,ticker):
    market='korea' if ticker.isdigit() else 'us'
    result=master.search(market,query)
    assert ticker in [r['ticker'] for r in result['data']]
    assert all(r['market']==market for r in result['data'])
    assert all('provider_symbol' not in r and 'search_name' not in r for r in result['data'])


def test_empty_unknown_limits_ranking_and_wildcards():
    assert master.search('us','')['data']==[]
    assert master.search('us','nothing-like-a-security')['data']==[]
    assert master.search('us','%%%')['data']==[]
    assert master.search('us','NVDA')['data'][0]['ticker']=='NVDA'
    assert len(master.search('korea','삼성',1)['data'])==1
    with pytest.raises(HTTPException):master.search('us','a\nquery')
    with pytest.raises(HTTPException):master.search('us','query',31)
    with pytest.raises(HTTPException):master.search('us','x'*101)


def test_yahoo_fallback_only_joins_master_and_suppresses_duplicates(monkeypatch):
    monkeypatch.setattr(master,'yahoo_candidates',lambda query:[('005930.KS','EQUITY'),('005930.KS','EQUITY'),('UNKNOWN','EQUITY'),('AAPL','EQUITY'),('069500.KS','EQUITY')])
    rows=master.search('korea','Samsung Electronics')['data']
    assert [r['ticker'] for r in rows]==['005930']
    assert rows[0]['name']=='삼성전자'


def test_source_parsers_type_status_and_exchange():
    rows,_=sources.parse_nasdaq(nasdaq_bytes([
        'NVDA|NVIDIA Common Stock|Q|N|N|100|N|N',
        'SPY|SPDR S&P 500 ETF|Q|N|N|100|Y|N',
        'BAD|Fixture Preferred Stock|Q|N|N|100|N|N',
        'TEST|Fixture Common Stock|Q|Y|N|100|N|N',
        'HALT|Fixture Common Stock|Q|N|D|100|N|N',
        'LEV|Fixture 3x ETF|Q|N|N|100|Y|N',
    ]),'nasdaq')
    assert {r['ticker'] for r in rows}=={'NVDA','SPY','HALT'}
    assert next(r for r in rows if r['ticker']=='SPY')['security_type']=='ETF'
    assert not next(r for r in rows if r['ticker']=='HALT')['active']
    rows,_=sources.parse_nasdaq(nasdaq_bytes(['BRK.A|Berkshire Common Stock|N|BRK.A|N|100|N|BRK.A'],True),'other')
    assert rows[0]['provider_symbol']=='BRK-A' and rows[0]['exchange']=='NYSE'
    payload=kis_bytes([('005930','삼성전자','ST',True,'0'),('005935','삼성전자우','ST',True,'1'),
                       ('069500','KODEX 200','EF',True,'0'),('123456','Fixture ETN','EN',True,'0'),
                       ('234567','정지 종목','ST',False,'0'),('345678','인버스 ETF','EF',True,'0')])
    rows=sources.parse_kis(payload,'kospi')
    assert {r['ticker'] for r in rows}=={'005930','069500','234567'}
    assert next(r for r in rows if r['ticker']=='069500')['security_type']=='ETF'
    assert not next(r for r in rows if r['ticker']=='234567')['active']
    assert all(r['provider_symbol'].endswith('.KS') for r in rows)
    assert sources.parse_kis(kis_bytes([('035900','JYP Ent.','ST',True,'0')],'kosdaq'),'kosdaq')[0]['provider_symbol']=='035900.KQ'


def test_bad_source_schema_and_duplicate_conflict(monkeypatch):
    with pytest.raises(ValueError):sources.parse_nasdaq(b'Symbol|Name\nNVDA|NVIDIA','nasdaq')
    with pytest.raises((ValueError,zipfile.BadZipFile)):sources.parse_kis(kis_bytes([('005930','a','ST',True,'0')])[:-10],'kospi')


def test_atomic_publish_failure_and_market_independence(security_directory):
    before=master.search('us','NVDA')
    korean=master.state('korea')
    with master.database() as db:
        db.execute("CREATE TRIGGER fail_directory BEFORE INSERT ON securities WHEN NEW.market='us' BEGIN SELECT RAISE(ABORT,'fixture'); END")
    with pytest.raises(sqlite3.IntegrityError):
        master.publish('us',[r for r in security_directory if r['market']=='us'],[],minimum=1)
    assert master.search('us','NVDA')==before
    assert master.state('korea')==korean


def test_refresh_failure_keeps_directory_but_stale_directory_cannot_trade(monkeypatch):
    def fail(*_):raise TimeoutError('fixture')
    monkeypatch.setattr(master,'fetch_market',fail)
    before=master.state('us')
    with pytest.raises(TimeoutError):master.refresh('us',force=True)
    assert master.state('us')==before
    with master.database() as db:
        db.execute("UPDATE directory_state SET refreshed_at=? WHERE market='us'",(time.time()-2*86400,));db.commit()
    assert master.search('us','NVDA')['directory_status']=='STALE'
    with pytest.raises(HTTPException) as error:master.resolve('us','NVDA')
    assert error.value.status_code==503
    with master.database() as db:
        db.execute("UPDATE directory_state SET refreshed_at=? WHERE market='us'",(time.time()-4*86400,));db.commit()
    with pytest.raises(HTTPException):master.search('us','NVDA')


def test_missing_directory_fails_closed(tmp_path,monkeypatch):
    monkeypatch.setenv('PAPER_SYMBOL_MASTER_PATH',str(tmp_path/'missing.sqlite3'))
    monkeypatch.setattr(master,'fetch_market',Mock(side_effect=TimeoutError))
    assert master.search('us','')['data']==[]
    with pytest.raises(HTTPException) as error:master.search('us','NVDA')
    assert error.value.status_code==503


@pytest.fixture
def clients(tmp_path,monkeypatch, zero_cost_policy):
    monkeypatch.setenv('PAPER_DB_PATH',str(tmp_path/'accounts.sqlite3'))
    monkeypatch.setenv('PAPER_SESSION_SECRET',secrets.token_urlsafe(48))
    monkeypatch.setenv('PAPER_ALLOWED_ORIGINS','http://testserver')
    monkeypatch.setenv('PAPER_COOKIE_SECURE','false')
    monkeypatch.setenv('PAPER_STARTING_USD','1000')
    monkeypatch.setenv('PAPER_STARTING_KRW','10000000')
    app=FastAPI();app.include_router(router)
    result=[]
    for username,role in [('admin1','admin'),('user1','user')]:
        password=secrets.token_urlsafe(32)
        provision_username_account(username,password,role=role)
        client=TestClient(app)
        assert client.post('/api/auth/login',json={'username':username,'password':password}).status_code==200
        result.append((client,client.get('/api/auth/me').json()['csrf_token']))
    return app,result


def test_authenticated_search_role_parity_and_bounded_api(clients):
    app,pairs=clients
    for market,query in [('us','PLTR'),('us','VOO'),('korea','삼성'),('korea','035420')]:
        results=[c.get('/api/paper/securities',params={'market':market,'q':query,'limit':2}) for c,_ in pairs]
        assert all(r.status_code==200 for r in results)
        assert results[0].json()==results[1].json()
        assert len(results[0].json()['data'])<=2
    assert TestClient(app).get('/api/paper/securities?market=us&q=NVDA').status_code==401
    client=pairs[0][0]
    assert client.get('/api/paper/securities?market=us&q=NVDA&limit=31').status_code==422
    assert client.get('/api/paper/securities?market=us&q='+('x'*101)).status_code==422
    assert client.get('/api/paper/quote?market=us&symbol=005930').status_code==422
    assert client.get('/api/paper/quote?market=korea&symbol=AAPL').status_code==422
    assert client.get('/api/paper/quote?market=us&symbol=UNKNOWN').status_code==422


@pytest.mark.parametrize('failure',[None,'currency','exchange','symbol','type','missing','stale','timeout'])
def test_quote_provider_validation(clients,monkeypatch,failure):
    import yfinance as yf
    metadata={'currency':'USD','symbol':'NVDA','instrumentType':'EQUITY','exchangeName':'NMS'}
    mutations={'currency':('currency','KRW'),'exchange':('exchangeName','KSC'),'symbol':('symbol','AAPL'),'type':('instrumentType','CRYPTOCURRENCY')}
    if failure in mutations:
        key,value=mutations[failure];metadata[key]=value
    class Ticker:
        history_metadata=metadata
        def history(self,**kwargs):
            if failure=='timeout':raise TimeoutError('fixture')
            if failure=='missing':return pd.DataFrame({'Close':[]},index=pd.DatetimeIndex([]))
            days=10 if failure=='stale' else 1
            day=datetime.now(ZoneInfo('America/New_York')).date()-timedelta(days=days)
            return pd.DataFrame({'Close':[100.]},index=pd.DatetimeIndex([day]))
    factory=Mock(return_value=Ticker());monkeypatch.setattr(yf,'Ticker',factory)
    client=clients[1][0][0]
    response=client.get('/api/paper/quote?market=us&symbol=NVDA')
    assert response.status_code==(200 if failure is None else 503)
    factory.assert_called_once_with('NVDA')
    with database() as db:assert db.execute('SELECT COUNT(*) FROM quotes').fetchone()[0]==(1 if failure is None else 0)


@pytest.mark.parametrize('market,input_symbol,stored', [('us','NVDA','NVDA'),('korea','035420','035420.KS'),('korea','035900','035900.KQ')])
def test_generalized_orders_accounting_and_isolation(clients,monkeypatch,market,input_symbol,stored):
    with database() as db:
        db.execute("UPDATE portfolios SET cash=10000000 WHERE market='korea'");db.commit()
    price=10000 if market=='us' else 50000
    def provider(m,s):return prices.Price(price,None,(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),int(time.time()))
    monkeypatch.setattr(prices,'fetch_price',provider)
    admin,csrf=clients[1][0];other,other_csrf=clients[1][1]
    def quote(c=admin):return c.get('/api/paper/quote',params={'market':market,'symbol':input_symbol}).json()['id']
    def order(side,quantity,c=admin,token=csrf,quote_id=None):
        selected=quote_id or quote(c)
        plan=c.get('/api/paper/settlement',params={'quote_id':selected,'side':side,'quantity':quantity})
        fields={key:plan.json()[key] for key in ['settlement_id','fx_usd_cents','fx_krw']} if plan.status_code==200 else {}
        return c.post('/api/paper/orders',json={'market':market,'symbol':input_symbol,'side':side,'quantity':quantity,'quote_id':selected,'request_key':str(uuid4()),**fields},headers={'x-csrf-token':token})
    def summary(c):return c.get('/api/paper/portfolio',params={'market':market}).json()
    initial=summary(admin)['cash']
    assert order('BUY',2).status_code==201
    assert summary(admin)['positions'][0]['symbol']==stored
    assert summary(admin)['cash']==initial-2*price/(100 if market=='us' else 1)
    assert summary(other)['cash']==initial and summary(other)['positions']==[]
    assert order('BUY',1,c=other,token=other_csrf,quote_id=quote()).status_code==409
    assert order('BUY',1000000).status_code==409
    assert order('SELL',3).status_code==409
    price*=2
    assert order('SELL',1).status_code==201
    assert summary(admin)['realized_pnl']>0
    assert len(admin.get('/api/paper/orders',params={'market':market}).json()['data'])==2
    assert other.get('/api/paper/orders',params={'market':market,'user_id':1}).json()['data']==[]
    assert order('BUY',1,c=other,token=csrf).status_code==403


def test_complete_source_merge_deduplicates_and_rejects_conflicts(monkeypatch):
    row=sources.entry('us','NVDA','NVIDIA Common Stock','Nasdaq','Stock')
    monkeypatch.setattr(sources,'download',lambda url:(b'fixture',None))
    monkeypatch.setattr(sources,'parse_nasdaq',lambda content,source:([row],'fixture'))
    result,provenance=sources.fetch_market('us')
    assert result==[row] and len(provenance)==2
    conflicting={**row,'exchange':'NYSE'}
    monkeypatch.setattr(sources,'parse_nasdaq',lambda content,source:([row if source=='nasdaq' else conflicting],'fixture'))
    with pytest.raises(ValueError,match='Conflicting'):sources.fetch_market('us')


def test_shrink_rejected_and_halted_listing_not_tradable(security_directory):
    before=master.state('us')
    with pytest.raises(ValueError,match='shrink'):
        master.publish('us',[security_directory[0]],[],minimum=1)
    assert master.state('us')==before
    rows=[r for r in security_directory if r['market']=='us']
    rows=[{**r,'active':False} if r['symbol']=='NVDA' else r for r in rows]
    master.publish('us',rows,[],minimum=1)
    assert all(row['ticker']!='NVDA' for row in master.search('us','NVDA')['data'])
    with pytest.raises(HTTPException) as error:master.resolve('us','NVDA')
    assert error.value.status_code==422


@pytest.mark.parametrize('market,symbol,provider,exchange,kind',[
    ('us','PLTR','PLTR','NMS','EQUITY'),('us','VOO','VOO','PCX','ETF'),
    ('korea','069500','069500.KS','KSC','ETF'),('korea','035900','035900.KQ','KOE','EQUITY'),
])
def test_stock_etf_provider_mapping_and_short_price_cache(clients,monkeypatch,market,symbol,provider,exchange,kind):
    import yfinance as yf
    class Ticker:
        history_metadata={'currency':'USD' if market=='us' else 'KRW','symbol':provider,'exchangeName':exchange,'instrumentType':kind}
        def history(self,**kwargs):
            day=datetime.now(ZoneInfo('America/New_York' if market=='us' else 'Asia/Seoul')).date()-timedelta(days=1)
            return pd.DataFrame({'Close':[100.]},index=pd.DatetimeIndex([day]))
    factory=Mock(return_value=Ticker());monkeypatch.setattr(yf,'Ticker',factory)
    first=clients[1][0][0].get('/api/paper/quote',params={'market':market,'symbol':symbol})
    second=clients[1][1][0].get('/api/paper/quote',params={'market':market,'symbol':symbol})
    assert first.status_code==second.status_code==200
    assert first.json()['symbol']==second.json()['symbol']==provider
    assert first.json()['id']!=second.json()['id']
    factory.assert_called_once_with(provider)


def test_directory_io_failure_is_a_safe_unavailable_response(monkeypatch):
    monkeypatch.setattr(master,'refresh',Mock(side_effect=sqlite3.OperationalError('fixture')))
    with pytest.raises(HTTPException) as error:master.ensure_current('us')
    assert error.value.status_code==503


def test_yahoo_name_lookup_is_bounded_filtered_and_cached(monkeypatch):
    import yfinance as yf
    query='offline nvidia lookup fixture'
    result=Mock(quotes=[
        {'symbol':'NVDA','quoteType':'EQUITY','longname':query},
        {'symbol':'BTC-USD','quoteType':'CRYPTOCURRENCY','longname':query},
        {'symbol':'MSFT','quoteType':'EQUITY','longname':'An unrelated company'},
    ])
    provider=Mock(return_value=result);monkeypatch.setattr(yf,'Search',provider)
    assert YAHOO_LOOKUP(query)==[('NVDA','EQUITY')]
    assert YAHOO_LOOKUP(query)==[('NVDA','EQUITY')]
    provider.assert_called_once()
    assert provider.call_args.kwargs['max_results']==8
    assert provider.call_args.kwargs['timeout']==4
    assert provider.call_args.kwargs['recommended']==0
    provider.side_effect=TimeoutError('fixture')
    assert YAHOO_LOOKUP('offline failed lookup fixture')==[]


@pytest.mark.parametrize('query,market,symbol', [
    ('AAPL','us','AAPL'),('QQQ','us','QQQ'),('PLTR','us','PLTR'),
    ('005930','korea','005930.KS'),('삼성전자','korea','005930.KS'),
    ('000660','korea','000660.KS'),
])
def test_unified_client_search_endpoints_preserve_role_parity(clients,query,market,symbol):
    """The unified picker composes these unchanged per-market API contracts."""
    results=[]
    for client,_ in clients[1]:
        combined=[]
        for book in ['us','korea']:
            response=client.get('/api/paper/securities',params={'market':book,'q':query,'limit':30})
            assert response.status_code==200
            combined.extend(response.json()['data'])
        results.append(combined)
    assert results[0]==results[1]
    assert any(row['market']==market and row['symbol']==symbol for row in results[0])


def test_us_quote_cannot_settle_against_korea_book(clients,monkeypatch):
    client,csrf=clients[1][1]
    monkeypatch.setattr(prices,'fetch_price',lambda market,symbol:prices.Price(10025,None,(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),int(time.time())))
    before={market:client.get('/api/paper/portfolio',params={'market':market}).json() for market in ['us','korea']}
    quote=client.get('/api/paper/quote',params={'market':'us','symbol':'QQQ'})
    assert quote.status_code==200
    response=client.post('/api/paper/orders',json={'market':'korea','symbol':'005930.KS','side':'BUY','quantity':5,'quote_id':quote.json()['id'],'request_key':str(uuid4())},headers={'x-csrf-token':csrf})
    assert response.status_code==409
    for market in ['us','korea']:
        after=client.get('/api/paper/portfolio',params={'market':market}).json()
        assert after['cash']==before[market]['cash'] and after['positions']==before[market]['positions']
