import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.paper import prices
from src.paper.router import router
from src.paper.store import database


@pytest.fixture
def workspace_env(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_DB_PATH', str(tmp_path / 'paper.sqlite3'))
    monkeypatch.setenv('PAPER_SESSION_SECRET', 'test-private-secret-' * 4)
    monkeypatch.setenv('PAPER_STARTING_USD', '1000')
    monkeypatch.setenv('PAPER_STARTING_KRW', '10000000')
    monkeypatch.setenv('PAPER_ALLOWED_ORIGINS', 'http://testserver')
    monkeypatch.setenv('PAPER_COOKIE_SECURE', 'false')
    marks = {'us': 10000, 'korea': 50000}
    def provider(market, symbol):
        prices.security(market, symbol)
        return prices.Price(marks[market], marks[market] - 100, (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), int(time.time()), 'Fixture close (test only)')
    monkeypatch.setattr(prices, 'fetch_price', provider)
    app = FastAPI()
    app.include_router(router)
    return app, marks


def account(app, email='a@example.com'):
    client = TestClient(app)
    response = client.post('/api/auth/register', json={'email': email, 'password': 'a-long-test-password'}, headers={'origin': 'http://testserver'})
    assert response.status_code == 201, response.text
    assert 'password' not in response.text
    assert 'HttpOnly' in response.headers['set-cookie']
    csrf = client.get('/api/auth/me').json()['csrf_token']
    return client, csrf


def quote(client, market='us', symbol='SPY'):
    response = client.get('/api/paper/quote', params={'market': market, 'symbol': symbol})
    assert response.status_code == 200, response.text
    return response.json()['id']


def order(client, csrf, side='BUY', quantity=1, symbol='SPY', market='us', quote_id=None, request_key=None):
    payload = {'market': market, 'symbol': symbol, 'side': side, 'quantity': quantity, 'quote_id': quote_id or quote(client, market, symbol), 'request_key': request_key or str(uuid4())}
    return client.post('/api/paper/orders', json=payload, headers={'x-csrf-token': csrf, 'origin': 'http://testserver'}), payload


def summary(client, market='us'):
    response = client.get('/api/paper/portfolio', params={'market': market})
    assert response.status_code == 200, response.text
    return response.json()


def test_accounts_sessions_and_isolation(workspace_env):
    app, _ = workspace_env
    a, csrf_a = account(app)
    b, csrf_b = account(app, 'b@example.com')
    assert order(a, csrf_a, quantity=2)[0].status_code == 201
    assert summary(a)['cash'] == 800
    assert summary(b)['cash'] == 1000
    assert summary(b)['positions'] == []
    assert b.get('/api/paper/orders?market=us&user_id=1').json()['data'] == []
    assert b.get('/api/paper/performance?market=us&user_id=1').json()['data'][0]['value'] == 1000
    assert order(b, csrf_b, quote_id=quote(a))[0].status_code == 409
    assert order(b, csrf_a)[0].status_code == 403
    assert b.get('/api/auth/me', headers={'origin':'https://evil.example'}).status_code == 403
    assert b.get('/api/paper/portfolio?market=us', headers={'origin':'https://evil.example'}).status_code == 403
    with database() as db:
        encoded = db.execute('SELECT password_hash FROM users WHERE email=?', ('a@example.com',)).fetchone()[0]
    assert encoded.startswith('scrypt$') and 'a-long-test-password' not in encoded
    assert a.post('/api/auth/logout', json={}, headers={'x-csrf-token': csrf_a}).status_code == 200
    assert a.get('/api/paper/portfolio?market=us').status_code == 401
    assert a.post('/api/auth/login', json={'email':'a@example.com','password':'wrong-password'}).status_code == 401
    assert a.post('/api/auth/login', json={'email':'a@example.com','password':'a-long-test-password'}).status_code == 200
    assert summary(a)['cash'] == 800
    anonymous = TestClient(app)
    assert anonymous.get('/api/paper/orders?market=us').status_code == 401
    assert anonymous.post('/api/auth/register', json={'email':'evil@example.com','password':'long-password'}, headers={'origin':'https://evil.example'}).status_code == 403


def test_average_cost_cash_pnl_and_full_exit(workspace_env):
    app, marks = workspace_env
    client, csrf = account(app)
    assert order(client, csrf, quantity=2)[0].status_code == 201
    marks['us'] = 20000
    assert order(client, csrf, quantity=2)[0].status_code == 201
    book = summary(client)
    assert book['positions'][0]['average_cost'] == 150
    assert book['cash'] == 400
    marks['us'] = 25000
    assert order(client, csrf, side='SELL')[0].status_code == 201
    book = summary(client)
    assert book['cash'] == 650
    assert book['positions'][0]['quantity'] == 3
    assert book['positions'][0]['average_cost'] == 150
    assert book['unrealized_pnl'] == 300
    assert book['realized_pnl'] == 100
    assert book['portfolio_value'] == 1400
    assert book['total_return_pct'] == 40
    assert book['today_pnl'] is None
    assert len(client.get('/api/paper/orders?market=us').json()['data']) == 3
    assert order(client, csrf, side='SELL', quantity=3)[0].status_code == 201
    book = summary(client)
    assert book['cash'] == 1400 and book['realized_pnl'] == 400
    assert book['positions'] == [] and book['unrealized_pnl'] == 0


@pytest.mark.parametrize('quantity', [0,-1,1.5,True,'2',1000001])
def test_invalid_quantities(workspace_env, quantity):
    app, _ = workspace_env
    client, csrf = account(app)
    assert order(client, csrf, quantity=quantity)[0].status_code == 422
    assert summary(client)['cash'] == 1000


def test_rejections_and_idempotency(workspace_env):
    app, _ = workspace_env
    client, csrf = account(app)
    assert order(client, csrf, quantity=11)[0].status_code == 409
    assert order(client, csrf, side='SELL')[0].status_code == 409
    assert client.get('/api/paper/quote?market=us&symbol=NOTREAL').status_code == 422
    assert client.get('/api/paper/quote?market=korea&symbol=SPY').status_code == 422
    response, payload = order(client, csrf, quantity=3)
    assert response.status_code == 201
    with database() as db:
        db.execute('UPDATE quotes SET expires_at=0')
        db.commit()
    # Accepted request retries are still recognized after the quote expires.
    retry = client.post('/api/paper/orders', json=payload, headers={'x-csrf-token':csrf})
    assert retry.status_code == 201 and retry.json()['id'] == response.json()['id']
    assert summary(client)['cash'] == 700
    assert len(client.get('/api/paper/orders?market=us').json()['data']) == 1
    changed = {**payload,'quantity':4}
    assert client.post('/api/paper/orders', json=changed, headers={'x-csrf-token':csrf}).status_code == 409
    assert order(client, csrf, quote_id=payload['quote_id'])[0].status_code == 409
    assert client.post('/api/paper/orders', json={**payload,'request_key':str(uuid4()),'execution_price':1}, headers={'x-csrf-token':csrf}).status_code == 422


def test_concurrent_retries_and_overspending(workspace_env):
    app, _ = workspace_env
    client, csrf = account(app)
    q = quote(client)
    payload = {'market':'us','symbol':'SPY','side':'BUY','quantity':6,'quote_id':q,'request_key':str(uuid4())}
    def submit(body):
        other = TestClient(app)
        other.cookies.update(client.cookies)
        return other.post('/api/paper/orders', json=body, headers={'x-csrf-token':csrf})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit,[payload,payload]))
    assert all(result.status_code == 201 for result in results)
    assert results[0].json()['id'] == results[1].json()['id']
    assert summary(client)['cash'] == 400
    payloads = [{**payload,'quantity':3,'request_key':str(uuid4())} for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit,payloads))
    assert sorted(result.status_code for result in results) == [201,409]
    assert summary(client)['cash'] == 100


def test_missing_stale_prices_and_quote_expiry(workspace_env, monkeypatch):
    app, _ = workspace_env
    client, csrf = account(app)
    assert order(client, csrf)[0].status_code == 201
    def unavailable(*_):
        raise HTTPException(503,'Price source unavailable')
    monkeypatch.setattr(prices,'fetch_price',unavailable)
    assert client.get('/api/paper/quote?market=us&symbol=SPY').status_code == 503
    book = summary(client)
    assert not book['valuation_complete'] and book['portfolio_value'] is None
    assert book['cash'] == 900 and book['positions'][0]['latest_price'] is None
    def stale(*_):
        return prices.Price(10000,None,(datetime.now(timezone.utc)-timedelta(days=10)).isoformat(),int(time.time()))
    monkeypatch.setattr(prices,'fetch_price',stale)
    assert client.get('/api/paper/quote?market=us&symbol=SPY').status_code == 503


def test_korea_currency_and_session_expiry(workspace_env):
    app, _ = workspace_env
    client, csrf = account(app)
    assert order(client, csrf, market='korea', symbol='005930.KS', quantity=10)[0].status_code == 201
    book = summary(client,'korea')
    assert book['currency'] == 'KRW' and book['cash'] == 9500000
    assert book['positions'][0]['average_cost'] == 50000
    assert summary(client)['cash'] == 1000
    with database() as db:
        db.execute('UPDATE sessions SET expires_at=0')
        db.commit()
    assert client.get('/api/auth/me').status_code == 401


def test_rounding_preserves_total_cost_and_recorded_daily_pnl(workspace_env):
    app, marks = workspace_env
    client, csrf = account(app)
    marks['us'] = 1001
    assert order(client, csrf, quantity=3)[0].status_code == 201
    marks['us'] = 1002
    assert order(client, csrf, quantity=2)[0].status_code == 201
    marks['us'] = 1005
    assert order(client, csrf, side='SELL', quantity=2)[0].status_code == 201
    with database() as db:
        position = db.execute('SELECT cost_basis FROM positions').fetchone()
        assert position['cost_basis'] == 3004  # 5007 total basis less 2003 allocated.
        portfolio_id = db.execute("SELECT id FROM portfolios WHERE market='us'").fetchone()[0]
        yesterday = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
        db.execute('INSERT INTO snapshots (portfolio_id,observed_at,value,cash) VALUES (?,?,?,?)', (portfolio_id,yesterday,100000,100000))
        db.commit()
    book = summary(client)
    assert book['realized_pnl'] == .07
    assert book['unrealized_pnl'] == .11
    assert book['today_pnl'] == .18
    assert order(client, csrf, side='SELL', quantity=3)[0].status_code == 201
    book = summary(client)
    assert book['positions'] == []
    assert book['realized_pnl'] == .18
    assert book['cash'] == 1000.18


def test_hash_salts_are_unique_and_auth_throttles(workspace_env):
    app, _ = workspace_env
    account(app)
    account(app,'b@example.com')
    with database() as db:
        hashes = [row[0] for row in db.execute('SELECT password_hash FROM users').fetchall()]
    assert hashes[0] != hashes[1]
    client = TestClient(app)
    for _ in range(15):
        assert client.post('/api/auth/login',json={'email':'unknown@example.com','password':'long-incorrect-password'}).status_code == 401
    assert client.post('/api/auth/login',json={'email':'unknown@example.com','password':'long-incorrect-password'}).status_code == 429
