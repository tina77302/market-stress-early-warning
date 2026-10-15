"""Password-only updates preserve identities, accounting records and sessions."""
import getpass
import secrets
import sqlite3
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin import reset_password
from src.paper import auth
from src.paper.accounts import provision_username_account
from src.paper.router import router
from src.paper.store import database


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    path = tmp_path/'paper.sqlite3'
    monkeypatch.setenv('PAPER_DB_PATH', str(path))
    monkeypatch.setenv('PAPER_SESSION_SECRET', secrets.token_urlsafe(48))
    monkeypatch.setenv('PAPER_ALLOWED_ORIGINS', 'http://testserver')
    monkeypatch.setenv('PAPER_COOKIE_SECURE', 'false')
    old_password = secrets.token_urlsafe(32)
    provision_username_account('admin1', old_password, role='admin')
    provision_username_account('user1', secrets.token_urlsafe(32))
    token = secrets.token_urlsafe(32)
    with database() as db:
        user = db.execute("SELECT id FROM users WHERE username='admin1'").fetchone()[0]
        db.execute('INSERT INTO sessions VALUES (?,?,?)', (auth.digest(token),user,int(time.time())+3600))
        portfolio = db.execute("SELECT id FROM portfolios WHERE user_id=? AND market='us'", (user,)).fetchone()[0]
        db.execute("INSERT INTO positions VALUES (?,'SPY',1,10000)", (portfolio,))
        db.execute("INSERT INTO quotes VALUES ('fixture-quote',?,'us','SPY',10000,9900,'fixture',1,2,'fixture')", (user,))
        db.execute("INSERT INTO orders (portfolio_id,user_id,request_key,market,symbol,side,quantity,execution_price,realized_pnl,quote_id,price_observed_at,executed_at) VALUES (?,?,'fixture-key','us','SPY','BUY',1,10000,0,'fixture-quote','fixture','fixture')", (portfolio,user))
        db.commit()
    return path, old_password, token


def snapshot(path):
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {t:[dict(r) for r in db.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in tables}


def run_cli(password, confirmation=None, username='admin1'):
    with patch.object(reset_password.sys.stdin, 'isatty', return_value=True), patch.object(reset_password.getpass, 'getpass', side_effect=[password,password if confirmation is None else confirmation]):
        return reset_password.main(['--username',username])


@pytest.mark.parametrize('username', ['admin1','user1'])
@pytest.mark.parametrize('length', [8,128])
def test_reset_only_changes_target_password(accounts, username, length, capsys, caplog):
    path, old_password, token = accounts
    before = snapshot(path)
    password = secrets.token_urlsafe(128)[:length]
    with patch.object(reset_password, 'password_hash', wraps=auth.password_hash) as hasher:
        assert run_cli(password, username=username.upper()) == 0
        hasher.assert_called_once_with(password)
    after = snapshot(path)
    old_user = next(u for u in before['users'] if u['username']==username)
    new_user = next(u for u in after['users'] if u['username']==username)
    assert auth.password_matches(password,new_user['password_hash'])
    assert new_user['password_hash'] != old_user['password_hash']
    assert password not in new_user['password_hash']
    # Compare every persisted field in every table after accounting for exactly
    # one permitted hash change; this includes USD/KRW portfolios and history.
    new_user['password_hash'] = old_user['password_hash']
    assert after == before
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    client.cookies.set(auth.COOKIE, token)
    assert client.get('/api/auth/me').json()['user']['username'] == 'admin1'
    if username=='admin1':
        assert client.post('/api/auth/login',json={'username':username,'password':old_password}).status_code == 401
    assert client.post('/api/auth/login',json={'username':username,'password':password}).status_code == 200
    output = capsys.readouterr()
    assert password not in output.out+output.err+caplog.text
    assert old_password not in output.out+output.err+caplog.text


@pytest.mark.parametrize('length', [7,129])
def test_invalid_length_preserves_database(accounts,length):
    path, _, _ = accounts
    before = snapshot(path)
    assert run_cli(secrets.token_urlsafe(128)[:length]) == 1
    assert snapshot(path) == before


def test_mismatch_unknown_and_nonterminal_preserve_database(accounts,capsys):
    path, _, _ = accounts
    before = snapshot(path)
    password = secrets.token_urlsafe(32)
    assert run_cli(password, secrets.token_urlsafe(32)) == 1
    with patch.object(reset_password.sys.stdin, 'isatty', return_value=True), patch.object(reset_password.getpass, 'getpass') as prompt:
        assert reset_password.main(['--username','missing']) == 1
        prompt.assert_not_called()
    with patch.object(reset_password.sys.stdin, 'isatty', return_value=False), patch.object(reset_password.getpass, 'getpass') as prompt:
        assert reset_password.main(['--username','admin1']) == 1
        prompt.assert_not_called()
    assert snapshot(path) == before
    assert password not in str(capsys.readouterr())


@pytest.mark.parametrize('error',[EOFError,KeyboardInterrupt,getpass.GetPassWarning])
def test_cancelled_or_insecure_prompt_preserves_database(accounts,error,capsys):
    path, _, _ = accounts
    before = snapshot(path)
    with patch.object(reset_password.sys.stdin, 'isatty', return_value=True), patch.object(reset_password.getpass, 'getpass', side_effect=error):
        assert reset_password.main(['--username','admin1']) == 1
    assert snapshot(path) == before


def test_password_arguments_rejected_without_echo(accounts,capsys):
    password = secrets.token_urlsafe(32)
    with pytest.raises(SystemExit) as result:
        reset_password.main(['--username','admin1','--password',password])
    assert result.value.code == 2
    output = capsys.readouterr()
    assert password not in output.out+output.err


def test_missing_database_never_created(tmp_path,monkeypatch):
    path = tmp_path/'missing'/'paper.sqlite3'
    monkeypatch.setenv('PAPER_DB_PATH',str(path))
    with patch.object(reset_password.sys.stdin, 'isatty', return_value=True), patch.object(reset_password.getpass, 'getpass') as prompt:
        assert reset_password.main(['--username','admin1']) == 1
        prompt.assert_not_called()
    assert not path.parent.exists()


def test_concurrent_password_reset_is_not_overwritten(accounts):
    path, _, _ = accounts
    password = secrets.token_urlsafe(32)
    concurrent = auth.password_hash(secrets.token_urlsafe(32))
    def prompt(_):
        with sqlite3.connect(path) as db:
            db.execute("UPDATE users SET password_hash=? WHERE username='admin1'",(concurrent,))
        return password
    with patch.object(reset_password.sys.stdin, 'isatty', return_value=True), patch.object(reset_password.getpass, 'getpass', side_effect=prompt):
        assert reset_password.main(['--username','admin1']) == 1
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT password_hash FROM users WHERE username='admin1'").fetchone()[0] == concurrent


def test_write_failure_rolls_back(accounts):
    path, _, _ = accounts
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER refuse_password_reset BEFORE UPDATE OF password_hash ON users BEGIN SELECT RAISE(ABORT,'fixture'); END")
    before = snapshot(path)
    assert run_cli(secrets.token_urlsafe(32)) == 1
    assert snapshot(path) == before
