"""Single capital, immutable FX provenance and transactional settlement; fully offline."""
import secrets
import sqlite3
import time
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from src.paper import fx,prices
from src.paper.accounts import provision_username_account
from src.paper.router import router
from src.paper.store import database
FETCH_OBSERVATION=fx.fetch_observation


@pytest.fixture
def investment_env(tmp_path,monkeypatch, zero_cost_policy):
    monkeypatch.setenv('PAPER_DB_PATH',str(tmp_path/'investment.sqlite3'))
    monkeypatch.setenv('PAPER_SESSION_SECRET',secrets.token_urlsafe(48))
    monkeypatch.setenv('PAPER_COOKIE_SECURE','false')
    monkeypatch.setenv('PAPER_ALLOWED_ORIGINS','http://testserver')
    monkeypatch.setenv('PAPER_STARTING_USD','999') # legacy environment must not duplicate/override capital
    monkeypatch.setenv('PAPER_STARTING_KRW','999999999')
    marks={'us':10000,'korea':50000}
    monkeypatch.setattr(prices,'fetch_price',lambda market,symbol:prices.Price(marks[market],None,(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),int(time.time())))
    app=FastAPI();app.include_router(router)
    clients=[]
    for name,role in [('admin1','admin'),('user1','user')]:
        password=secrets.token_urlsafe(24);provision_username_account(name,password,role=role)
        client=TestClient(app);assert client.post('/api/auth/login',json={'username':name,'password':password}).status_code==200
        clients.append((client,client.get('/api/auth/me').json()['csrf_token']))
    return clients,marks


def quote(client,market='korea',symbol='005930.KS'):
    response=client.get('/api/paper/quote',params={'market':market,'symbol':symbol});assert response.status_code==200,response.text
    return response.json()


def reviewed(client,quote,side='BUY',quantity=10):
    response=client.get('/api/paper/settlement',params={'quote_id':quote['id'],'side':side,'quantity':quantity});assert response.status_code==200,response.text
    return {'market':quote['market'],'symbol':quote['symbol'],'side':side,'quantity':quantity,'quote_id':quote['id'],'request_key':str(uuid4()),**{k:response.json()[k] for k in ['fx_usd_cents','fx_krw','settlement_id']}}


def submit(pair,body):return pair[0].post('/api/paper/orders',json=body,headers={'x-csrf-token':pair[1]})
def cash(client):return {market:client.get('/api/paper/portfolio',params={'market':market}).json()['cash'] for market in ['us','korea']}


def test_one_capital_and_role_parity(investment_env):
    pairs,_=investment_env
    for client,_ in pairs:
        data=client.get('/api/paper/investment').json()
        assert data['initial_capital']==data['portfolio_value']==100000
        assert data['cash_balances']=={'USD':100000,'KRW':0}
        assert data['total_pnl']==0 and data['base_currency']=='USD'
    with database() as db:
        assert db.execute('SELECT COUNT(*) FROM investment_accounts').fetchone()[0]==2
        assert all(row[0]==0 for row in db.execute("SELECT starting_cash FROM portfolios WHERE market='korea'"))


def test_korean_buy_sell_and_unified_value(investment_env):
    pairs,marks=investment_env;pair=pairs[1];client=pair[0]
    body=reviewed(client,quote(client));assert body['fx_usd_cents']==50000 and body['fx_krw']==500000
    assert submit(pair,body).status_code==201
    assert cash(client)=={'us':99500,'korea':0}
    summary=client.get('/api/paper/investment').json();assert summary['portfolio_value']==100000
    assert summary['books']['korea']['positions'][0]['quantity']==10
    marks['korea']=60000
    sell=reviewed(client,quote(client),'SELL',5);assert sell['fx_krw']==0
    assert submit(pair,sell).status_code==201
    assert cash(client)=={'us':99500,'korea':300000}
    data=client.get('/api/paper/investment').json();assert data['portfolio_value']==100100 and data['total_pnl']==100
    assert data['books']['korea']['realized_pnl']==50000
    assert data['books']['korea']['unrealized_pnl']==50000
    ledger=client.get('/api/paper/fx-ledger').json()['data'];assert len(ledger)==1
    assert ledger[0]['from_minor']==50000 and ledger[0]['to_minor']==500000 and ledger[0]['source']==fx.SOURCE
    assert cash(pairs[0][0])=={'us':100000,'korea':0}


def test_translation_moves_with_fx_without_native_price_change(investment_env,monkeypatch):
    pair=investment_env[0][1];client=pair[0];assert submit(pair,reviewed(client,quote(client))).status_code==201
    with database() as db:
        row=dict(db.execute('SELECT * FROM paper_fx_rates LIMIT 1').fetchone());row.update(id=str(uuid4()),rate='2000')
        db.execute('INSERT INTO paper_fx_rates VALUES (?,?,?,?,?)',tuple(row[k] for k in ['id','rate','observation_date','retrieved_at','source']));db.commit()
    monkeypatch.setattr(fx,'latest',lambda:row)
    data=client.get('/api/paper/investment').json();assert data['portfolio_value']==99750 and data['total_pnl']==-250
    assert data['books']['korea']['unrealized_pnl']==0


@pytest.mark.parametrize('kind',['missing','stale','future','retrieval','negative','nan'])
def test_invalid_fx_never_funds_korea(investment_env,monkeypatch,kind):
    pair=investment_env[0][0];client=pair[0]
    def unavailable():raise HTTPException(503,'FX unavailable')
    if kind=='missing':monkeypatch.setattr(fx,'latest',unavailable)
    else:
        row={'id':str(uuid4()),'rate':'1000','source':fx.SOURCE,'observation_date':datetime.now(timezone.utc).date().isoformat(),'retrieved_at':datetime.now(timezone.utc).isoformat()}
        if kind=='stale':row['observation_date']=(datetime.now(timezone.utc)-timedelta(days=11)).date().isoformat()
        if kind=='future':row['observation_date']=(datetime.now(timezone.utc)+timedelta(days=1)).date().isoformat()
        if kind=='retrieval':row['retrieved_at']=(datetime.now(timezone.utc)-timedelta(hours=7)).isoformat()
        if kind=='negative':row['rate']='-1'
        if kind=='nan':row['rate']='NaN'
        monkeypatch.setattr(fx,'fetch_observation',lambda:row)
    q=quote(client)
    assert client.get('/api/paper/settlement',params={'quote_id':q['id'],'side':'BUY','quantity':10}).status_code==503
    assert cash(client)=={'us':100000,'korea':0}


def test_unavailable_fx_does_not_hide_zero_krw_usd_capital(investment_env,monkeypatch):
    def fail():raise HTTPException(503,'FX unavailable')
    monkeypatch.setattr(fx,'latest',fail)
    data=investment_env[0][0][0].get('/api/paper/investment').json()
    assert data['portfolio_value']==100000 and data['fx'] is None


def test_unavailable_fx_blocks_nonzero_krw_valuation(investment_env,monkeypatch):
    pair=investment_env[0][0];client=pair[0];assert submit(pair,reviewed(client,quote(client))).status_code==201
    def fail():raise HTTPException(503,'FX unavailable')
    monkeypatch.setattr(fx,'latest',fail)
    before=client.get('/api/paper/investment').json()['performance']
    data=client.get('/api/paper/investment').json();assert data['portfolio_value'] is None and data['total_pnl'] is None
    assert data['performance']==before and not data['valuation_complete']


def test_explicit_conversion_consent_and_replay(investment_env):
    pair=investment_env[0][0];client=pair[0];body=reviewed(client,quote(client))
    bad={k:v for k,v in body.items() if k not in ['fx_usd_cents','fx_krw','settlement_id']}
    assert submit(pair,bad).status_code==409 and cash(client)['us']==100000
    result=submit(pair,body);assert result.status_code==201
    with database() as db:db.execute('UPDATE quotes SET expires_at=0');db.commit()
    retry=submit(pair,body);assert retry.status_code==201 and retry.json()['id']==result.json()['id']
    assert submit(pair,{**body,'fx_krw':body['fx_krw']+1}).status_code==409
    assert len(client.get('/api/paper/fx-ledger').json()['data'])==1


def test_transaction_rollback_after_fx_debit(investment_env):
    pair=investment_env[0][0];body=reviewed(pair[0],quote(pair[0]))
    with database() as db:
        db.execute("CREATE TRIGGER injected_failure BEFORE INSERT ON orders BEGIN SELECT RAISE(ABORT,'test rollback'); END");db.commit()
    with pytest.raises(sqlite3.IntegrityError):submit(pair,body)
    assert cash(pair[0])=={'us':100000,'korea':0}
    with database() as db:
        assert db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM paper_fx_ledger').fetchone()[0]==0


def test_concurrent_duplicate_conversion_once(investment_env):
    pair=investment_env[0][0];body=reviewed(pair[0],quote(pair[0]))
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:submit(pair,body),[1,2]))
    assert all(r.status_code==201 for r in responses) and responses[0].json()['id']==responses[1].json()['id']
    assert cash(pair[0])=={'us':99500,'korea':0}
    assert len(pair[0].get('/api/paper/fx-ledger').json()['data'])==1


def test_reverse_topup_and_reuse_native_cash(investment_env):
    pair=investment_env[0][0];client=pair[0]
    with database() as db:
        db.execute("UPDATE portfolios SET cash=50000 WHERE user_id=1 AND market='us'")
        db.execute("UPDATE portfolios SET cash=500000 WHERE user_id=1 AND market='korea'");db.commit()
    body=reviewed(client,quote(client,'us','QQQ'),quantity=10)
    assert body['fx_usd_cents']==50000 and body['fx_krw']==500000
    assert submit(pair,body).status_code==201 and cash(client)=={'us':0,'korea':0}
    ledger=client.get('/api/paper/fx-ledger').json()['data'][0];assert ledger['from_currency']=='KRW'


def test_owner_cannot_use_other_fx_quote(investment_env):
    pairs,_=investment_env;q=quote(pairs[0][0]);body=reviewed(pairs[0][0],q)
    assert pairs[1][0].get('/api/paper/settlement',params={'quote_id':q['id'],'side':'BUY','quantity':10}).status_code==409
    assert submit(pairs[1],body).status_code==409


def test_legacy_account_is_never_silently_recapitalized(investment_env):
    pair=investment_env[0][0];client=pair[0]
    with database() as db:
        db.execute('DELETE FROM investment_snapshots WHERE user_id=1');db.execute('DELETE FROM investment_accounts WHERE user_id=1');db.commit()
        before=[tuple(r) for r in db.execute('SELECT * FROM portfolios WHERE user_id=1')]
    assert client.get('/api/paper/investment').status_code==409
    with database() as db:assert [tuple(r) for r in db.execute('SELECT * FROM portfolios WHERE user_id=1')]==before


def test_fx_provider_parses_actual_dates_and_missing_markers(monkeypatch):
    from unittest.mock import Mock
    now=datetime.now(timezone.utc).date().isoformat();response=Mock();response.json.return_value={'observations':[{'date':now,'value':'.'},{'date':now,'value':'1342.13'}]}
    monkeypatch.setenv('FRED_API_KEY','test-only-never-logged');monkeypatch.setattr(fx.requests,'get',lambda *a,**k:response)
    # conftest replaces fetch_observation; import a fresh function from the file for the boundary test.
    result=FETCH_OBSERVATION();assert result['rate']=='1342.13' and result['observation_date']==now


def test_existing_schema_upgrade_preserves_every_financial_row(tmp_path,monkeypatch):
    from src.paper.store import SCHEMA
    path=tmp_path/'legacy.sqlite3';monkeypatch.setenv('PAPER_DB_PATH',str(path))
    db=sqlite3.connect(path);db.executescript(SCHEMA.replace('CHECK(starting_cash>=0)','CHECK(starting_cash>0)'))
    db.execute('CREATE INDEX legacy_cash_lookup ON portfolios(user_id,market,cash)')
    db.execute("INSERT INTO users VALUES (42,NULL,'hash-preserved','past','admin1','admin')")
    db.execute("INSERT INTO portfolios VALUES (91,42,'us','USD',10000000,9000000,4,100,'past')")
    db.execute("INSERT INTO portfolios VALUES (92,42,'korea','KRW',100000000,100000000,0,0,'past')")
    db.execute("INSERT INTO positions VALUES (91,'QQQ',2,1000000)")
    db.execute("INSERT INTO orders VALUES (7,91,42,'key','us','QQQ','BUY',2,500000,0,'old','past','past')")
    db.execute("INSERT INTO snapshots VALUES (5,91,'past',10000000,9000000)")
    db.commit();tables=['users','portfolios','positions','orders','snapshots'];before={t:db.execute('SELECT * FROM '+t).fetchall() for t in tables};db.close()
    with database() as upgraded:
        assert {t:[tuple(r) for r in upgraded.execute('SELECT * FROM '+t)] for t in tables}==before
        assert not upgraded.execute('PRAGMA foreign_key_check').fetchall()
        assert upgraded.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_cash_lookup'").fetchone()
        assert not upgraded.execute('SELECT * FROM investment_accounts').fetchall()


def test_conversion_minor_unit_rounding_preserves_remainder(investment_env,monkeypatch):
    pair=investment_env[0][0];client=pair[0];investment_env[1]['korea']=1001
    with database() as db:
        row=dict(db.execute('SELECT * FROM paper_fx_rates LIMIT 1').fetchone()) if db.execute('SELECT COUNT(*) FROM paper_fx_rates').fetchone()[0] else fx.fetch_observation()
        row.update(id=str(uuid4()),rate='1333');db.execute('INSERT INTO paper_fx_rates VALUES (?,?,?,?,?)',tuple(row[k] for k in ['id','rate','observation_date','retrieved_at','source']));db.commit()
    monkeypatch.setattr(fx,'latest',lambda:row)
    body=reviewed(client,quote(client),quantity=1)
    assert body['fx_usd_cents']==76 and body['fx_krw']==1013
    assert submit(pair,body).status_code==201
    assert cash(client)=={'us':99999.24,'korea':12}
    event=client.get('/api/paper/fx-ledger').json()['data'][0]
    assert event['usd_cash_after']==9999924 and event['krw_cash_after']==12 and event['quantity_after']==1



def test_read_only_audit_never_exposes_credentials_or_changes_rows(investment_env,capsys):
    from src.admin.audit_portfolios import main
    with database() as db:before=list(db.iterdump())
    main();out=capsys.readouterr().out
    assert 'admin1' in out and 'user1' in out and 'READ_ONLY' in out
    assert 'password_hash' not in out and 'scrypt$' not in out and 'token_hash' not in out
    with database() as db:assert list(db.iterdump())==before
