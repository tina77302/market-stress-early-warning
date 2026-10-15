"""Production-default costs and locked preview accounting; no live provider calls."""
import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi import HTTPException
from src.paper import costs, fx
from src.paper.store import database
from tests.test_unified_investment import investment_env, quote, reviewed, submit, cash


@pytest.fixture
def real_env(investment_env, monkeypatch):
    monkeypatch.delenv('PAPER_COST_CONFIG_PATH', raising=False)
    monkeypatch.setattr(costs, 'trade_date', lambda market: '2026-10-15')
    return investment_env


def policy():
    return json.loads(Path(costs.__file__).with_name('cost_rules.json').read_text())


def preview(client, q, side='BUY', quantity=10):
    result=client.get('/api/paper/settlement',params={'quote_id':q['id'],'side':side,'quantity':quantity})
    assert result.status_code==200,result.text
    return result.json()


@pytest.mark.parametrize('market,kind,exchange,side,day,commission,tax,regulatory',[
    ('us','Stock','NASDAQ','BUY','2026-10-15',0,0,0),
    ('us','Stock','NASDAQ','SELL','2026-10-15',0,0,3),
    ('us','ETF','NASDAQ','SELL','2026-10-15',0,0,3),
    ('us','Stock','NASDAQ','SELL','2026-04-03',0,0,1),
    ('us','Stock','NASDAQ','SELL','2026-04-04',0,0,4),
    ('us','Stock','NASDAQ','SELL','2026-09-30',0,0,4),
    ('us','Stock','NASDAQ','SELL','2026-10-01',0,0,3),
    ('korea','Stock','KOSPI','BUY','2026-10-15',75,0,0),
    ('korea','Stock','KOSPI','SELL','2026-10-15',75,1000,0),
    ('korea','Stock','KOSDAQ','SELL','2026-10-15',75,1000,0),
    ('korea','ETF','KOSPI','SELL','2026-10-15',75,0,0),
])
def test_default_dated_fee_matrix(market,kind,exchange,side,day,commission,tax,regulatory):
    result=costs.breakdown(costs.validate(policy()),market,kind,exchange,side,10000 if market=='us' else 50000,10,day)
    assert (result['commission_minor'],result['transaction_tax_minor'],result['regulatory_fee_minor'])==(commission,tax,regulatory)
    assert result['total_fees_minor']==commission+tax+regulatory


@pytest.mark.parametrize('mutation',[
    lambda p:p.update(fx_spread_bps='NaN'),
    lambda p:p.update(fx_spread_bps='-1'),
    lambda p:p.update(version=''),
    lambda p:p.update(sources={}),
    lambda p:p['commission_bps']['us']['Stock'].update(BUY='Infinity'),
    lambda p:p['commission_min_minor'].update(us=True),
    lambda p:p['korea_stock_sell_taxes']['KOSPI'].clear(),
    lambda p:p['us_sec'].append(p['us_sec'][0]),
])
def test_invalid_policies_fail_closed(mutation):
    data=policy();mutation(data)
    with pytest.raises(HTTPException) as error:costs.validate(data)
    assert error.value.status_code==503


def test_expired_or_unknown_classification():
    for day,exchange in [('2027-01-01','KOSPI'),('2026-10-15','UNKNOWN')]:
        with pytest.raises(HTTPException):costs.breakdown(policy(),'korea','Stock',exchange,'SELL',50000,10,day)


def test_korea_costs_balances_pnl_and_idempotency(real_env,monkeypatch):
    pairs,marks=real_env;pair=pairs[1];client=pair[0];q=quote(client)
    plan=preview(client,q)
    assert plan['costs']['gross_minor']==500000
    assert plan['costs']['commission_minor']==75
    assert plan['total_cash_effect']==500075
    assert plan['effective_fx_rate']=='999.000'
    assert plan['remaining_cash']=={'USD':99499.42,'KRW':4}
    body=reviewed(client,q)
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:submit(pair,body),range(2)))
    assert all(r.status_code==201 for r in responses)
    assert responses[0].json()['id']==responses[1].json()['id']
    assert cash(client)=={'us':99499.42,'korea':4}
    data=client.get('/api/paper/investment').json()
    assert data['portfolio_value']==99999.42
    with database() as db:
        records=[dict(row) for row in db.execute('SELECT * FROM paper_order_costs')]
        rates=[dict(row) for row in db.execute('SELECT * FROM paper_fx_rates')]
        events=[dict(row) for row in db.execute('SELECT * FROM paper_fx_ledger')]
        assert len(records)==len(events)==1
        assert records[0]['fx_cost_usd']=='0.501'
        db.execute('UPDATE quotes SET expires_at=0');db.commit()
    assert submit(pair,body).status_code==201
    marks['korea']=60000
    assert submit(pair,reviewed(client,quote(client),'SELL',10)).status_code==201
    assert cash(client)=={'us':99499.42,'korea':598714}
    data=client.get('/api/paper/investment').json()
    assert data['portfolio_value']==100098.13
    assert data['books']['korea']['realized_pnl']==98635
    assert cash(pairs[0][0])=={'us':100000,'korea':0}
    with database() as db:
        assert dict(db.execute('SELECT * FROM paper_order_costs ORDER BY order_id LIMIT 1').fetchone())==records[0]
        assert [dict(r) for r in db.execute('SELECT * FROM paper_fx_rates')]==rates
        assert [dict(r) for r in db.execute('SELECT * FROM paper_fx_ledger')]==events
    # A new valuation reference must never rewrite historical execution economics.
    from uuid import uuid4
    changed_rate={**rates[0],'id':str(uuid4()),'rate':'2000'}
    with database() as db:
        db.execute('INSERT INTO paper_fx_rates VALUES (?,?,?,?,?)',tuple(changed_rate[k] for k in ['id','rate','observation_date','retrieved_at','source']));db.commit()
    monkeypatch.setattr(fx,'latest',lambda:changed_rate)
    assert client.get('/api/paper/investment').json()['portfolio_value']==99798.78
    with database() as db:
        assert dict(db.execute('SELECT * FROM paper_order_costs ORDER BY order_id LIMIT 1').fetchone())==records[0]
        assert [dict(r) for r in db.execute('SELECT * FROM paper_fx_ledger')]==events


def test_reverse_fx_spread_and_insufficient_cash(real_env):
    pair=real_env[0][0];client=pair[0]
    with database() as db:
        db.execute("UPDATE portfolios SET cash=50000 WHERE user_id=1 AND market='us'")
        db.execute("UPDATE portfolios SET cash=500000 WHERE user_id=1 AND market='korea'");db.commit()
    q=quote(client,'us','AAPL')
    assert client.get('/api/paper/settlement',params={'quote_id':q['id'],'side':'BUY','quantity':10}).status_code==409
    with database() as db:db.execute("UPDATE portfolios SET cash=600000 WHERE user_id=1 AND market='korea'");db.commit()
    plan=preview(client,q)
    assert plan['effective_fx_rate']=='1001.000'
    assert plan['fx_krw']==500500 and plan['fx_usd_cents']==50000
    assert submit(pair,reviewed(client,q)).status_code==201
    assert cash(client)=={'us':0,'korea':99500}


def test_us_sell_net_regulatory_fee(real_env):
    pair=real_env[0][0];client=pair[0]
    assert submit(pair,reviewed(client,quote(client,'us','AAPL'))).status_code==201
    q=quote(client,'us','AAPL');plan=preview(client,q,'SELL')
    assert plan['costs']['regulatory_fee_minor']==3 and plan['total_cash_effect']==999.97
    assert submit(pair,reviewed(client,q,'SELL')).status_code==201
    assert cash(client)['us']==99999.97
    assert client.get('/api/paper/investment').json()['books']['us']['realized_pnl']==-.03


def test_policy_frozen_preview_owner_and_cash_change(real_env,tmp_path,monkeypatch):
    pair=real_env[0][0];client=pair[0];q=quote(client)
    changed=copy.deepcopy(policy());changed['commission_bps']['korea']['Stock']['BUY']='10'
    path=tmp_path/'costs.json';path.write_text(json.dumps(changed));monkeypatch.setenv('PAPER_COST_CONFIG_PATH',str(path))
    assert preview(client,q)['costs']['commission_minor']==75
    assert preview(client,quote(client))['costs']['commission_minor']==500
    body=reviewed(client,q)
    assert submit(real_env[0][1],body).status_code in (404,409)
    with database() as db:db.execute("UPDATE portfolios SET cash=cash-1 WHERE user_id=1 AND market='us'");db.commit()
    assert submit(pair,body).status_code==409
    with database() as db:assert db.execute('SELECT COUNT(*) FROM paper_order_costs').fetchone()[0]==0


def test_cost_record_failure_rolls_back_every_posting(real_env):
    pair=real_env[0][0];body=reviewed(pair[0],quote(pair[0]))
    with database() as db:
        db.execute("CREATE TRIGGER cost_failure BEFORE INSERT ON paper_order_costs BEGIN SELECT RAISE(ABORT,'injected cost failure'); END");db.commit()
    with pytest.raises(sqlite3.IntegrityError):submit(pair,body)
    assert cash(pair[0])=={'us':100000,'korea':0}
    with database() as db:
        for table in ['orders','positions','paper_fx_ledger','paper_order_costs']:
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==0
