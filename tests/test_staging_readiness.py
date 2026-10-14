"""Deployment invariants using isolated files; no model training or live providers."""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from src import runtime
from src.operations import store, refresh, scheduler
from scripts import staging_state


@pytest.fixture
def operations(tmp_path, monkeypatch):
    root = tmp_path / 'ebs/data/operations'
    monkeypatch.setenv('MARKET_OPERATIONS_DIR', str(root))
    return root


def test_staging_fails_closed_and_development_defaults(monkeypatch):
    for name in ['APP_ENV', 'PAPER_ALLOWED_ORIGINS', 'PAPER_COOKIE_SECURE', 'PAPER_SESSION_SECRET', 'MARKET_DATA_ROOT', 'MARKET_MODELS_ROOT']:
        monkeypatch.delenv(name, raising=False)
    assert not runtime.secure_cookie()
    assert 'http://localhost:3000' in runtime.allowed_origins()
    runtime.validate_runtime()
    monkeypatch.setenv('APP_ENV', 'staging')
    assert runtime.secure_cookie() and runtime.allowed_origins() == []
    with pytest.raises(RuntimeError): runtime.validate_runtime()
    monkeypatch.setenv('PAPER_SESSION_SECRET', 'test-only-secret-with-at-least-32-characters')
    monkeypatch.setenv('MARKET_DATA_ROOT', '/app/data')
    monkeypatch.setenv('MARKET_MODELS_ROOT', '/app/models')
    for origin in ['', 'http://localhost:3000', 'https://example.test/path', 'https://user@example.test', 'https://example.test?q=1']:
        monkeypatch.setenv('PAPER_ALLOWED_ORIGINS', origin)
        with pytest.raises(RuntimeError): runtime.validate_runtime()
    monkeypatch.setenv('PAPER_ALLOWED_ORIGINS', 'https://example.test')
    runtime.validate_runtime()
    monkeypatch.setenv('PAPER_COOKIE_SECURE', 'false')
    with pytest.raises(RuntimeError): runtime.validate_runtime()


def test_cookie_set_and_delete_share_secure_defaults(monkeypatch):
    from src.paper import auth
    from fastapi import Response
    monkeypatch.setenv('APP_ENV', 'staging')
    monkeypatch.delenv('PAPER_COOKIE_SECURE', raising=False)
    assert auth.secure_cookie()
    response = Response()
    response.delete_cookie(auth.COOKIE, secure=auth.secure_cookie(), httponly=True, samesite='lax', path='/')
    assert 'Secure' in response.headers['set-cookie']


def test_new_and_legacy_paths_rebase_without_changing_snapshot(operations, monkeypatch):
    stage = operations / 'staging/job123'
    stage.mkdir(parents=True)
    source = stage / 'source_history.csv'
    source.write_text('Date,SPY\n2026-10-09,100\n')
    payload = {'last_updated': '2026-10-09', 'artifact_directory': '/old/machine/data/operations/staging/job123',
               'source_history_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    with store.database() as db:
        db.execute("INSERT INTO jobs (job_id,market,trigger,started_at,status) VALUES ('job123','us','manual',?,'RUNNING')", (store.utcnow(),))
    identity = store.publish('job123', 'us', payload)
    assert refresh.seeds('us')['SPY'].iloc[0, 0] == 100
    assert store.snapshot('us')['snapshot_id'] == identity
    assert store.snapshot('us')['payload'] == payload
    assert store.artifact_reference(stage) == 'staging/job123'
    assert store.artifact_path('staging/job123') == stage.resolve()
    source.write_text('Date,SPY\n2026-10-09,999\n')
    with pytest.raises(refresh.ValidationFailure): refresh.seeds('us')
    for path in ['../../elsewhere', '/unknown/root/data', 'staging/../../../escape']:
        with pytest.raises(ValueError): store.artifact_path(path)


def test_scheduler_lease_blocks_another_process_and_releases(operations):
    command = [sys.executable, '-c', 'from src.operations.scheduler import SchedulerLease; lease=SchedulerLease(); lease.close()']
    with scheduler.SchedulerLease():
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        assert result.returncode != 0 and 'already owns' in result.stderr
        with pytest.raises(RuntimeError): scheduler.SchedulerLease()
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_configurable_roots_in_fresh_process(tmp_path):
    env = {**os.environ, 'MARKET_DATA_ROOT': str(tmp_path / 'data'), 'MARKET_MODELS_ROOT': str(tmp_path / 'models')}
    script = "from src.config import DATA_DIR,MODELS_DIR; print(DATA_DIR); print(MODELS_DIR)"
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [str(tmp_path / 'data'), str(tmp_path / 'models/saved')]


def test_online_wal_backup_and_restore_preserve_sessions_and_history(tmp_path):
    data = tmp_path / 'data'
    paper = data / 'paper/workspace.sqlite3'
    paper.parent.mkdir(parents=True)
    with sqlite3.connect(paper) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE sessions (token_hash TEXT, expires_at INTEGER)')
        db.execute('INSERT INTO sessions VALUES (?,?)', ('test-token-hash', 9999999999))
        db.commit()
        bundle = tmp_path / 'backup'
        bundle.mkdir()
        staging_state.backup(data, bundle)
        # The open WAL writer remains usable, but the backup captures committed state.
        db.execute('INSERT INTO sessions VALUES (?,?)', ('later-token', 9999999999))
        db.commit()
    destination = tmp_path / 'new-ebs/data'
    staging_state.restore(bundle, destination)
    with sqlite3.connect(destination / 'paper/workspace.sqlite3') as db:
        assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT * FROM sessions').fetchall() == [('test-token-hash', 9999999999)]
    with pytest.raises(ValueError): staging_state.restore(bundle, destination)
    (bundle / 'data/paper/workspace.sqlite3').write_bytes(b'tampered')
    with pytest.raises(ValueError): staging_state.restore(bundle, tmp_path / 'tampered-restore')


def test_backup_legacy_snapshot_history_is_portable(operations, tmp_path, monkeypatch):
    stage = operations / 'staging/job'
    stage.mkdir(parents=True)
    (stage / 'source_history.csv').write_text('Date,SPY\n2026-10-09,100\n')
    with store.database() as db:
        db.execute("INSERT INTO jobs (job_id,market,trigger,started_at,status) VALUES ('job','us','manual',?,'RUNNING')", (store.utcnow(),))
    original = {'last_updated': '2026-10-09', 'artifact_directory': '/old/data/operations/staging/job'}
    identity = store.publish('job', 'us', original)
    bundle = tmp_path / 'backup'
    bundle.mkdir()
    staging_state.backup(operations.parent, bundle)
    destination = tmp_path / 'restored/data'
    staging_state.restore(bundle, destination)
    monkeypatch.setenv('MARKET_OPERATIONS_DIR', str(destination / 'operations'))
    assert store.snapshot('us')['snapshot_id'] == identity
    assert store.snapshot('us')['payload'] == original
    assert refresh.seeds('us')['SPY'].iloc[0, 0] == 100
    assert store.history('us')[0]['status'] == 'SUCCESS'


def test_artifact_export_is_allowlisted_and_has_required_korea(tmp_path):
    data, models, bundle = tmp_path / 'data', tmp_path / 'models', tmp_path / 'bundle'
    for name in staging_state.REQUIRED:
        path = data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('existing-artifact')
    for name in staging_state.MODELS:
        path = models / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'existing-frozen-model')
    (data / '.env.staging').write_text('SECRET=must-not-export')
    (data / 'paper').mkdir()
    (data / 'paper/workspace.sqlite3').write_bytes(b'private-account-state')
    bundle.mkdir()
    staging_state.export_artifacts(data, models, bundle)
    manifest = json.loads((bundle / 'manifest.json').read_text())
    assert 'data/processed/korea/korea_targets.csv' in manifest['files']
    assert not any('.env' in name or 'paper/' in name for name in manifest['files'])
    staging_state.restore(bundle, tmp_path / 'fresh/data', tmp_path / 'fresh/models')
    assert (tmp_path / 'fresh/data/raw/korea/vkospi.csv').read_text() == 'existing-artifact'
