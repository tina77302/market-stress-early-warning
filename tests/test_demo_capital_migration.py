"""Authorized demo reset, immutable identity and role-independent trading."""
import secrets
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from src.admin.migrate_demo_portfolios import migrate_demo_portfolios, main
from src.paper.store import database
from tests.test_unified_investment import investment_env, quote, reviewed, submit, cash


def rows(db,table):
    return [tuple(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]


def register_third(client):
    third=TestClient(client.app)
    response=third.post('/api/auth/register',json={'email':'third@example.invalid','password':secrets.token_urlsafe(24)})
    assert response.status_code==201,response.text
    return third,third.get('/api/auth/me').json()['csrf_token']


def clean_state(client):
    value=client.get('/api/paper/investment');assert value.status_code==200,value.text
    data=value.json()
    assert data['base_currency']=='USD'
    assert data['initial_capital']==data['portfolio_value']==data['cash']==100000
    assert data['cash_balances']=={'USD':100000,'KRW':0}
    assert data['total_pnl']==data['total_return_pct']==data['invested_value']==0
    assert data['realized_pnl_usd_translated']==data['unrealized_pnl_usd_translated']==0
    assert data['cumulative_fees']=={'USD':0,'KRW':0}
    assert data['cumulative_fees_usd_translated']==data['fx_conversion_costs_usd']==0
    assert data['cost_ledger']==data['fx_conversions']==[]
    for market in ['us','korea']:
        assert data['books'][market]['positions']==[]
        assert data['books'][market]['realized_pnl']==data['books'][market]['unrealized_pnl']==0
        assert client.get('/api/paper/orders',params={'market':market}).json()['data']==[]
    return data


def test_existing_demo_reset_preserves_identity_and_new_registration_parity(investment_env,monkeypatch):
    pairs,_=investment_env
    from src.paper.admin import router as admin_router
    pairs[0][0].app.include_router(admin_router)
    monkeypatch.delenv('PAPER_COST_CONFIG_PATH',raising=False)
    from src.paper import costs
    monkeypatch.setattr(costs,'trade_date',lambda market:'2026-10-15')
    # Populate both demo accounts with real simulated orders, cost records and FX.
    old_requests=[]
    for pair in pairs:
        body=reviewed(pair[0],quote(pair[0]));old_requests.append(body)
        assert submit(pair,body).status_code==201
    with database() as db:
        # Reproduce the old dual-funded state, including no unified root for user1.
        db.execute("UPDATE portfolios SET starting_cash=100000000,cash=cash+100000000 WHERE market='korea'")
        db.execute('DELETE FROM investment_snapshots WHERE user_id=2')
        db.execute('DELETE FROM investment_accounts WHERE user_id=2')
        db.commit()
        protected={table:rows(db,table) for table in ['users','sessions','login_attempts','admin_activity','paper_fx_rates']}
        old_orders=rows(db,'orders');old_fx=rows(db,'paper_fx_ledger')
    result=migrate_demo_portfolios()
    assert result['status']=='APPLIED'
    backup=Path(result['backup']);assert backup.stat().st_mode & 0o777==0o600
    with sqlite3.connect(backup) as db:
        assert rows(db,'orders')==old_orders and rows(db,'paper_fx_ledger')==old_fx
    with database() as db:
        assert {table:rows(db,table) for table in protected}==protected
        for table in ['orders','positions','quotes','paper_quote_fx','paper_quote_costs','paper_order_previews','paper_order_costs','paper_fx_ledger']:
            assert rows(db,table)==[]
        assert db.execute('SELECT COUNT(*) FROM investment_accounts').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM paper_capital_migrations').fetchone()[0]==2
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    # Existing authenticated sessions still work; role and IDs are unchanged.
    assert pairs[0][0].get('/api/auth/me').json()['user']['role']=='admin'
    assert pairs[1][0].get('/api/auth/me').json()['user']['role']=='user'
    assert [p[0].get('/api/auth/me').json()['user']['id'] for p in pairs]==[1,2]
    for pair,old_body in zip(pairs,old_requests):
        clean_state(pair[0])
        assert submit(pair,old_body).status_code==409
    third=register_third(pairs[0][0]);assert third[0].get('/api/auth/me').json()['user']['role']=='user'
    clean_state(third[0]);all_pairs=[*pairs,third]
    # Both discovery universes, reference price quality, fees, FX and executions match.
    for market,symbol,side,quantity in [('us','AAPL','BUY',2),('korea','005930.KS','BUY',2),('korea','005930.KS','SELL',1),('us','AAPL','SELL',1)]:
        directories=[p[0].get('/api/paper/securities',params={'market':market,'q':symbol.split('.')[0]}).json() for p in all_pairs]
        assert directories[0]==directories[1]==directories[2]
        plans=[]
        for pair in all_pairs:
            q=quote(pair[0],market,symbol)
            response=pair[0].get('/api/paper/settlement',params={'quote_id':q['id'],'side':side,'quantity':quantity})
            assert response.status_code==200,response.text
            plan=response.json();plans.append({k:v for k,v in plan.items() if k not in ('quote_id','settlement_id')})
            assert submit(pair,reviewed(pair[0],q,side=side,quantity=quantity)).status_code==201
        assert plans[0]==plans[1]==plans[2]
    summaries=[p[0].get('/api/paper/investment').json() for p in all_pairs]
    for key in ['portfolio_value','cash_balances','total_pnl','realized_pnl_usd_translated','unrealized_pnl_usd_translated','cumulative_fees','fx_conversion_costs_usd']:
        assert summaries[0][key]==summaries[1][key]==summaries[2][key]
    # A repeat invocation/startup must not wipe the trades just made.
    before=[cash(p[0]) for p in all_pairs]
    assert migrate_demo_portfolios()['status']=='ALREADY_APPLIED'
    assert [cash(p[0]) for p in all_pairs]==before
    assert pairs[1][0].get('/api/admin/overview').status_code==403
    assert pairs[0][0].get('/api/admin/overview').status_code==200


def test_unrelated_user_history_untouched(investment_env):
    third=register_third(investment_env[0][0][0])
    assert submit(third,reviewed(third[0],quote(third[0]))).status_code==201
    with database() as db:
        before={table:rows(db,table) for table in ['users','sessions','paper_fx_rates']}
        holdings=[tuple(r) for r in db.execute('SELECT * FROM portfolios WHERE user_id=3')]
        orders=[tuple(r) for r in db.execute('SELECT * FROM orders WHERE user_id=3')]
        events=[tuple(r) for r in db.execute('SELECT * FROM paper_fx_ledger WHERE user_id=3')]
    migrate_demo_portfolios()
    with database() as db:
        assert {table:rows(db,table) for table in before}==before
        assert [tuple(r) for r in db.execute('SELECT * FROM portfolios WHERE user_id=3')]==holdings
        assert [tuple(r) for r in db.execute('SELECT * FROM orders WHERE user_id=3')]==orders
        assert [tuple(r) for r in db.execute('SELECT * FROM paper_fx_ledger WHERE user_id=3')]==events


def test_reset_failure_rolls_back_both_accounts(investment_env):
    for pair in investment_env[0]:assert submit(pair,reviewed(pair[0],quote(pair[0]))).status_code==201
    with database() as db:
        tables=['users','sessions','portfolios','positions','orders','snapshots','investment_accounts','investment_snapshots','paper_fx_ledger','paper_order_costs','quotes','paper_capital_migrations']
        before={table:rows(db,table) for table in tables}
        db.execute("CREATE TRIGGER migration_failure BEFORE INSERT ON investment_accounts WHEN NEW.user_id=2 BEGIN SELECT RAISE(ABORT,'injected failure'); END")
        db.commit()
    with pytest.raises(sqlite3.IntegrityError):migrate_demo_portfolios()
    with database() as db:assert {table:rows(db,table) for table in tables}==before


def test_concurrent_migration_once(investment_env):
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:migrate_demo_portfolios(),range(2)))
    assert sorted(r['status'] for r in results)==['ALREADY_APPLIED','APPLIED']
    for pair in investment_env[0]:clean_state(pair[0])


def test_missing_or_wrong_role_account_fails_without_changes(investment_env,capsys):
    with database() as db:
        db.execute("UPDATE users SET username='different' WHERE id=2");db.commit()
        before={table:rows(db,table) for table in ['users','portfolios','sessions']}
    assert main([])==1
    assert 'no partial trading reset' in capsys.readouterr().out
    with database() as db:
        assert {table:rows(db,table) for table in before}==before
        db.execute("UPDATE users SET username='user1',role='admin' WHERE id=2");db.commit()
    with pytest.raises(ValueError,match='roles'):migrate_demo_portfolios()
