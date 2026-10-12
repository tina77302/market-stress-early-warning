import os
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.paper import auth
from src.paper.admin import bootstrap_admin, provision_admin, router as admin_router
from src.paper.router import router as account_router
from src.paper.store import database


@pytest.fixture
def admin_env(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_DB_PATH', str(tmp_path / 'admin.sqlite3'))
    monkeypatch.setenv('PAPER_SESSION_SECRET', secrets.token_urlsafe(48))
    monkeypatch.setenv('PAPER_COOKIE_SECURE', 'false')
    monkeypatch.setenv('PAPER_ALLOWED_ORIGINS', 'http://testserver')
    monkeypatch.delenv('ADMIN_EMAIL', raising=False)
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    monkeypatch.delenv('ADMIN_BOOTSTRAP_PROMOTE_EXISTING', raising=False)
    return monkeypatch


def make_app():
    @asynccontextmanager
    async def lifespan(app):
        bootstrap_admin()
        yield
    app = FastAPI(lifespan=lifespan)
    app.include_router(account_router)
    app.include_router(admin_router)
    return app


def configure(monkeypatch):
    password = secrets.token_urlsafe(32)
    monkeypatch.setenv('ADMIN_EMAIL', 'owner@example.invalid')
    monkeypatch.setenv('ADMIN_PASSWORD', password)
    return password


def login(client, password):
    response = client.post('/api/auth/login', json={'email':'owner@example.invalid','password':password})
    assert response.status_code == 200
    assert response.json()['user']['role'] == 'admin'
    return client.get('/api/auth/me').json()['csrf_token']


def test_bootstrap_idempotent_hash_and_restart(admin_env, caplog, capsys):
    password = configure(admin_env)
    assert bootstrap_admin() == 'created'
    with database() as db:
        first = dict(db.execute('SELECT * FROM users').fetchone())
    assert first['role'] == 'admin'
    assert auth.password_matches(password,first['password_hash'])
    assert password not in first['password_hash']
    assert bootstrap_admin() == 'already_exists'
    app = make_app()
    for _ in range(2):
        with TestClient(app) as client:
            login(client,password)
            response = client.get('/api/admin/overview')
            assert response.status_code == 200
            assert response.json()['total_users'] == 1
            assert response.json()['total_portfolios'] == 2
    with database() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
        assert db.execute('SELECT password_hash FROM users').fetchone()[0] == first['password_hash']
    assert password not in caplog.text
    captured = capsys.readouterr()
    assert password not in captured.out + captured.err


def test_role_checks_redaction_and_no_impersonation(admin_env):
    password = configure(admin_env)
    with TestClient(make_app()) as admin:
        login(admin,password)
        user = TestClient(admin.app)
        signup = user.post('/api/auth/register',json={'email':'normal@example.invalid','password':secrets.token_urlsafe(24)})
        assert signup.status_code == 201 and signup.json()['user']['role'] == 'user'
        assert user.get('/api/auth/me').json()['user']['role'] == 'user'
        assert user.get('/api/admin/overview').status_code == 403
        assert user.get('/api/admin/users').status_code == 403
        anonymous = TestClient(admin.app)
        assert anonymous.get('/api/admin/overview').status_code == 401
        assert anonymous.get('/api/admin/users').status_code == 401
        for path in ['/api/admin/overview','/api/admin/users']:
            response = admin.get(path)
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-store'
            for forbidden in ['password_hash','token_hash','csrf_token',password]:
                assert forbidden not in response.text
        overview = admin.get('/api/admin/overview').json()
        assert overview['total_users'] == 2 and overview['total_portfolios'] == 4
        assert overview['accounts_with_unexpired_sessions'] == 2
        users = admin.get('/api/admin/users?limit=1&offset=1').json()
        assert users['total'] == 2 and len(users['data']) == 1
        assert users['data'][0]['role'] == 'user'
        assert users['data'][0]['portfolio_count'] == 2
        assert admin.get('/api/admin/users?limit=101').status_code == 422
        assert user.post('/api/auth/register',json={'email':'escalate@example.invalid','password':secrets.token_urlsafe(24),'role':'admin'}).status_code == 422
        assert admin.post('/api/admin/users',json={}).status_code == 405
        assert admin.delete('/api/admin/users').status_code == 405
        # Administrator still gets only their own paper data, even with caller-supplied IDs.
        assert admin.get('/api/paper/orders?market=us&user_id=2').json()['data'] == []
        assert admin.get('/api/paper/portfolio?market=us&user_id=2').json()['market'] == 'us'
        assert admin.get('/api/admin/overview',headers={'origin':'https://evil.example'}).status_code == 403
        # Add another independent admin; the final administrator cannot be demoted.
        provision_admin('second@example.invalid', secrets.token_urlsafe(32))
        # DB role changes take effect immediately, without issuing another session.
        with database() as db:
            db.execute("UPDATE users SET role='user' WHERE email='owner@example.invalid'")
            db.commit()
        assert admin.get('/api/admin/overview').status_code == 403


def test_existing_user_requires_explicit_promotion_and_preserves_password(admin_env):
    original_password = secrets.token_urlsafe(32)
    with TestClient(make_app()) as user:
        assert user.post('/api/auth/register',json={'email':'owner@example.invalid','password':original_password}).status_code == 201
    with database() as db:
        original_hash = db.execute('SELECT password_hash FROM users').fetchone()[0]
    configured_password = configure(admin_env)
    with pytest.raises(RuntimeError, match='Explicit') as error:
        bootstrap_admin()
    assert configured_password not in str(error.value)
    admin_env.setenv('ADMIN_BOOTSTRAP_PROMOTE_EXISTING','true')
    assert bootstrap_admin() == 'promoted_password_preserved'
    with database() as db:
        row = db.execute('SELECT * FROM users').fetchone()
        assert row['password_hash'] == original_hash and row['role'] == 'admin'
        assert db.execute('SELECT COUNT(*) FROM portfolios').fetchone()[0] == 2
    with TestClient(make_app()) as client:
        login(client,original_password)
        assert client.post('/api/auth/login',json={'email':'owner@example.invalid','password':configured_password}).status_code == 401


def test_old_database_migration_preserves_normal_users(admin_env):
    encoded = auth.password_hash(secrets.token_urlsafe(24))
    with sqlite3.connect(os.environ['PAPER_DB_PATH']) as db:
        db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL)')
        db.execute('INSERT INTO users VALUES (1,?,?,?)',('legacy@example.invalid',encoded,datetime.now(timezone.utc).isoformat()))
    for _ in range(2):
        with database() as db:
            row = db.execute('SELECT * FROM users').fetchone()
            assert row['role'] == 'user' and row['password_hash'] == encoded
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("UPDATE users SET role='invalid' WHERE id=1")


def test_missing_invalid_bootstrap_configuration_is_secret_safe(admin_env):
    assert bootstrap_admin() == 'not_configured'
    password = secrets.token_urlsafe(32)
    admin_env.setenv('ADMIN_PASSWORD',password)
    with pytest.raises(RuntimeError) as error:
        bootstrap_admin()
    assert password not in str(error.value)
    admin_env.setenv('ADMIN_EMAIL','owner@example.invalid')
    admin_env.setenv('ADMIN_PASSWORD','short')
    with pytest.raises(RuntimeError):
        bootstrap_admin()
