"""Username identity, persisted-role authorization and stable-ID ownership."""
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin.create_admin import main as admin_cli
from src.admin.create_user import main as user_cli
from src.paper import auth, prices
from src.paper.accounts import provision_username_account
from src.paper.admin import router as admin_router
from src.paper.router import router
from src.paper.store import SCHEMA, database


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_DB_PATH', str(tmp_path/'accounts.sqlite3'))
    monkeypatch.setenv('MARKET_OPERATIONS_DIR', str(tmp_path/'operations'))
    monkeypatch.setenv('PAPER_SESSION_SECRET', secrets.token_urlsafe(48))
    monkeypatch.setenv('PAPER_COOKIE_SECURE', 'false')
    monkeypatch.setenv('PAPER_ALLOWED_ORIGINS', 'http://testserver')
    monkeypatch.delenv('ADMIN_EMAIL', raising=False)
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    marks = {'us': 10000, 'korea': 50000}
    def price(market, symbol):
        return prices.Price(marks[market], marks[market]-100,
                            (datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),
                            int(time.time()), 'Fixture')
    monkeypatch.setattr(prices, 'fetch_price', price)
    app = FastAPI()
    app.include_router(router)
    app.include_router(admin_router)
    return app, marks


def logged_in(app, username, password, field='username'):
    client = TestClient(app)
    response = client.post('/api/auth/login', json={field: username, 'password': password})
    assert response.status_code == 200, response.text
    assert 'password' not in response.text
    assert 'HttpOnly' in response.headers['set-cookie']
    return client, client.get('/api/auth/me').json()['csrf_token']


@pytest.mark.parametrize('username,role', [('admin1','admin'), ('user1','user'), ('admin-impostor','user')])
def test_username_auth_role_hash_duplicates(accounts, username, role):
    app, _ = accounts
    password = secrets.token_urlsafe(32)
    provision_username_account(username, password, role=role)
    client, _ = logged_in(app, username.upper(), password)
    user = client.get('/api/auth/me').json()['user']
    assert user['username'] == username and user['role'] == role and user['email'] is None
    for endpoint in ('overview', 'users', 'data-health'):
        assert client.get('/api/admin/'+endpoint).status_code == (200 if role=='admin' else 403)
    with database() as db:
        original = dict(db.execute('SELECT * FROM users').fetchone())
        assert original['password_hash'].startswith('scrypt$')
        assert password not in str(original)
        assert auth.password_matches(password, original['password_hash'])
        assert db.execute('SELECT COUNT(*) FROM portfolios WHERE user_id=?', (user['id'],)).fetchone()[0] == 2
    with pytest.raises(ValueError, match='already exists'):
        provision_username_account(username.upper(), secrets.token_urlsafe(32), role='admin')
    with database() as db:
        assert dict(db.execute('SELECT * FROM users').fetchone()) == original
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('INSERT INTO users (username,password_hash,created_at) VALUES (?,?,?)', (username.upper(), 'unused', 'fixture'))
    assert client.post('/api/auth/login', json={'username':username,'password':secrets.token_urlsafe(32)}).status_code == 401


def test_persisted_role_and_username_are_independent(accounts):
    app, _ = accounts
    password = secrets.token_urlsafe(32)
    provision_username_account('admin-impostor', password)
    client, _ = logged_in(app, 'admin-impostor', password)
    assert client.get('/api/admin/overview').status_code == 403
    with database() as db:
        db.execute("UPDATE users SET username='ordinary-owner',role='admin' WHERE username='admin-impostor'")
        db.commit()
    # An existing session re-reads the persisted role; no username rule grants it.
    assert client.get('/api/admin/overview').status_code == 200
    provision_username_account('second-owner', secrets.token_urlsafe(32), role='admin')
    with database() as db:
        db.execute("UPDATE users SET role='user' WHERE username='ordinary-owner'")
        db.commit()
    assert client.get('/api/admin/overview').status_code == 403


def test_email_login_and_signup_role_protection(accounts):
    app, _ = accounts
    client = TestClient(app)
    password = secrets.token_urlsafe(32)
    body = {'email':'existing@example.invalid', 'password':password}
    assert client.post('/api/auth/register', json={**body, 'role':'admin'}).status_code == 422
    assert client.post('/api/auth/register', json=body).status_code == 201
    client, _ = logged_in(app, 'EXISTING@example.invalid', password, field='email')
    assert client.get('/api/auth/me').json()['user']['role'] == 'user'
    assert client.get('/api/admin/overview').status_code == 403
    assert client.post('/api/auth/register', json={'email':'admin-looking', 'password':password}).status_code == 422


@pytest.mark.parametrize('market,symbol', [('us','SPY'), ('korea','005930.KS')])
def test_admin_user_portfolio_order_pnl_and_history_isolation(accounts, market, symbol):
    app, marks = accounts
    passwords = [secrets.token_urlsafe(32), secrets.token_urlsafe(32)]
    provision_username_account('admin1', passwords[0], role='admin')
    provision_username_account('user1', passwords[1])
    admin, admin_csrf = logged_in(app, 'admin1', passwords[0])
    user, user_csrf = logged_in(app, 'user1', passwords[1])
    def summary(client, **params):
        return client.get('/api/paper/portfolio', params={'market':market, **params}).json()
    initial = summary(user)
    def quote(client):
        return client.get('/api/paper/quote', params={'market':market,'symbol':symbol}).json()['id']
    def order(client, csrf, side, quote_id=None, **extra):
        return client.post('/api/paper/orders', json={'market':market,'symbol':symbol,'side':side,'quantity':1,
                           'quote_id':quote_id or quote(client),'request_key':str(uuid4()), **extra},
                           headers={'x-csrf-token':csrf})
    assert order(admin, admin_csrf, 'BUY').status_code == 201
    marks[market] *= 2
    assert summary(admin)['unrealized_pnl'] > 0
    assert order(admin, admin_csrf, 'SELL').status_code == 201
    admin_book = summary(admin)
    assert admin_book['realized_pnl'] > 0 and admin_book['cash'] > initial['cash']
    assert summary(user)['cash'] == initial['cash']
    assert summary(user)['positions'] == []
    assert summary(user)['realized_pnl'] == summary(user)['unrealized_pnl'] == 0
    admin_id = admin.get('/api/auth/me').json()['user']['id']
    user_id = user.get('/api/auth/me').json()['user']['id']
    with database() as db:
        admin_portfolio_id = db.execute('SELECT id FROM portfolios WHERE user_id=? AND market=?', (admin_id,market)).fetchone()[0]
    for endpoint in ('orders', 'positions', 'performance'):
        own = user.get('/api/paper/'+endpoint, params={'market':market}).json()
        assert user.get('/api/paper/'+endpoint, params={'market':market,'user_id':admin_id,'portfolio_id':admin_portfolio_id}).json() == own
    assert summary(user, user_id=admin_id)['cash'] == initial['cash']
    assert order(user, user_csrf, 'BUY', quote_id=quote(admin)).status_code == 409
    assert order(user, user_csrf, 'SELL').status_code == 409
    assert order(user, user_csrf, 'BUY', user_id=admin_id).status_code == 422
    assert order(user, admin_csrf, 'BUY').status_code == 403
    assert order(user, user_csrf, 'BUY').status_code == 201
    assert summary(admin, user_id=user_id)['cash'] == admin_book['cash']
    assert len(admin.get('/api/paper/orders',params={'market':market}).json()['data']) == 2
    assert len(user.get('/api/paper/orders',params={'market':market}).json()['data']) == 1
    assert user.get('/api/paper/performance',params={'market':market}).json()['data']
    # Renaming identity does not detach or transfer a portfolio.
    with database() as db:
        db.execute("UPDATE users SET username='renamed-user' WHERE id=?", (user_id,))
        db.commit()
    assert summary(user)['positions'][0]['quantity'] == 1


def test_username_final_admin_and_anonymous_security(accounts):
    app, _ = accounts
    provision_username_account('admin1', secrets.token_urlsafe(32), role='admin')
    with database() as db:
        for sql in ("UPDATE users SET role='user'", 'DELETE FROM users'):
            with pytest.raises(sqlite3.IntegrityError, match='final administrator'):
                db.execute(sql)
    anonymous = TestClient(app)
    for path in ['/api/auth/me', '/api/admin/overview', '/api/admin/users', '/api/paper/portfolio?market=us',
                 '/api/paper/orders?market=us', '/api/paper/positions?market=us', '/api/paper/performance?market=us']:
        assert anonymous.get(path).status_code == 401


@pytest.mark.parametrize('command,username,role', [(admin_cli,'admin1','admin'), (user_cli,'user1','user')])
def test_secure_username_cli(accounts, command, username, role, capsys, caplog):
    password = secrets.token_urlsafe(32)
    with patch('src.admin.create_admin.sys.stdin.isatty', return_value=True), patch('src.admin.create_admin.getpass.getpass', side_effect=[password,password]) as prompt:
        assert command(['--username',username]) == 0
        assert prompt.call_count == 2
    with database() as db:
        assert db.execute('SELECT role FROM users WHERE username=?',(username,)).fetchone()[0] == role
    with patch('src.admin.create_admin.sys.stdin.isatty', return_value=True), patch('src.admin.create_admin.getpass.getpass', side_effect=[password,password]):
        assert command(['--username',username]) == 1
    captured = capsys.readouterr()
    assert 'User ID already exists' in captured.err
    assert password not in captured.out+captured.err+caplog.text
    with patch('src.admin.create_admin.sys.stdin.isatty', return_value=False):
        assert command(['--username','other']) == 1
    with patch('src.admin.create_admin.sys.stdin.isatty', return_value=True), patch('src.admin.create_admin.getpass.getpass', side_effect=[password,secrets.token_urlsafe(32)]):
        assert command(['--username','other']) == 1
    with pytest.raises(SystemExit):
        command(['--username','other','--password',password])
    captured = capsys.readouterr()
    assert password not in captured.out+captured.err+caplog.text
    with database() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1


def test_legacy_migration_preserves_identity_and_every_owned_table(accounts, monkeypatch, tmp_path):
    path = tmp_path/'legacy.sqlite3'
    monkeypatch.setenv('PAPER_DB_PATH',str(path))
    password = secrets.token_urlsafe(32)
    token = secrets.token_urlsafe(32)
    encoded = auth.password_hash(password)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')))")
    connection.executescript(SCHEMA)
    connection.execute("INSERT INTO users VALUES (42,'legacy@example.invalid',?,'fixture','admin')",(encoded,))
    connection.execute('INSERT INTO sessions VALUES (?,?,?)',(auth.digest(token),42,int(time.time())+3600))
    connection.execute("INSERT INTO portfolios VALUES (9,42,'us','USD',100000,90000,1,0,'fixture')")
    connection.execute("INSERT INTO positions VALUES (9,'SPY',1,10000)")
    connection.execute("INSERT INTO quotes VALUES ('quote',42,'us','SPY',10000,9900,'fixture',1,2,'fixture')")
    connection.execute("INSERT INTO orders VALUES (7,9,42,'key','us','SPY','BUY',1,10000,0,'quote','fixture','fixture')")
    connection.execute("INSERT INTO snapshots VALUES (3,9,'fixture',100000,90000)")
    connection.execute("INSERT INTO admin_activity VALUES (1,42,'admin.bootstrap_created',42,'fixture')")
    tables = ['users','sessions','portfolios','positions','quotes','orders','snapshots','admin_activity']
    before = {t:[dict(r) for r in connection.execute('SELECT * FROM '+t)] for t in tables}
    connection.commit(); connection.close()
    for _ in range(3):
        with database() as db:
            for table in tables:
                after = [dict(r) for r in db.execute('SELECT * FROM '+table)]
                if table=='users':
                    assert after[0].pop('username') is None
                assert after == before[table]
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
            with pytest.raises(sqlite3.IntegrityError, match='final administrator'):
                db.execute("UPDATE users SET role='user' WHERE id=42")
    app, _ = accounts
    client = TestClient(app)
    client.cookies.set(auth.COOKIE,token)
    assert client.get('/api/auth/me').json()['user']['id'] == 42
    logged_in(app,'legacy@example.invalid',password,field='email')
    provision_username_account('user1',secrets.token_urlsafe(32))
    with database() as db:
        assert db.execute("SELECT user_id FROM portfolios WHERE id=9").fetchone()[0] == 42


def test_migration_failure_rolls_back_legacy_users(accounts, monkeypatch, tmp_path):
    path = tmp_path/'broken-legacy.sqlite3'
    monkeypatch.setenv('PAPER_DB_PATH',str(path))
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL)')
        db.execute("INSERT INTO users VALUES (42,'legacy@example.invalid','fixture-hash','fixture')")
        db.executescript(SCHEMA)
        # A pre-existing broken reference must fail closed, never discard records.
        db.execute("INSERT INTO portfolios VALUES (9,999,'us','USD',100000,90000,1,0,'fixture')")
    with pytest.raises(RuntimeError, match='relationship integrity'):
        with database():
            pytest.fail('Broken migration must never yield an application connection')
    with sqlite3.connect(path) as db:
        columns = {r[1]:r for r in db.execute('PRAGMA table_info(users)')}
        assert 'username' not in columns and columns['email'][3] == 1
        assert db.execute('SELECT id,email,password_hash FROM users').fetchone() == (42,'legacy@example.invalid','fixture-hash')
        assert db.execute('SELECT user_id FROM portfolios').fetchone()[0] == 999


@pytest.mark.parametrize('length', [7, 8, 128, 129])
@pytest.mark.parametrize('command,flag,identity,role', [
    (admin_cli, '--username', 'admin1', 'admin'),
    (user_cli, '--username', 'user1', 'user'),
    (admin_cli, '--email', 'admin1@example.invalid', 'admin'),
])
def test_password_length_cli_and_login(accounts, command, flag, identity, role, length, capsys, caplog):
    password = secrets.token_urlsafe(128)[:length]
    valid = 8 <= length <= 128
    with patch('src.admin.create_admin.sys.stdin.isatty', return_value=True), patch('src.admin.create_admin.getpass.getpass', side_effect=[password,password]) as prompt:
        assert command([flag, identity]) == (0 if valid else 1)
        assert prompt.call_args_list[0].args[0] == 'Password (8–128 characters): '
        assert prompt.call_count == 2
    with database() as db:
        rows = db.execute('SELECT * FROM users').fetchall()
        assert len(rows) == int(valid)
        if valid:
            assert rows[0]['role'] == role
            assert auth.password_matches(password, rows[0]['password_hash'])
            assert password not in rows[0]['password_hash']
    if valid:
        client, _ = logged_in(accounts[0], identity, password, field='email' if flag=='--email' else 'username')
        assert client.get('/api/auth/me').json()['user']['role'] == role
    captured = capsys.readouterr()
    assert password not in captured.out+captured.err+caplog.text


@pytest.mark.parametrize('length', [7, 8, 128, 129])
def test_email_signup_password_length(accounts, length):
    password = secrets.token_urlsafe(128)[:length]
    body = {'email':'length@example.invalid','password':password}
    client = TestClient(accounts[0])
    valid = 8 <= length <= 128
    assert client.post('/api/auth/register', json=body).status_code == (201 if valid else 422)
    assert client.post('/api/auth/login', json=body).status_code == (200 if valid else 422)
