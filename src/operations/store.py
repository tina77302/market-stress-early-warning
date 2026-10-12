"""Durable ledger and one-transaction last-known-good publication."""
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from src.config import PROJECT_ROOT


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def root():
    return Path(os.getenv('MARKET_OPERATIONS_DIR', str(PROJECT_ROOT / 'data/operations')))


@contextmanager
def database():
    root().mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root() / 'refresh.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS jobs (
      job_id TEXT PRIMARY KEY, market TEXT NOT NULL, trigger TEXT NOT NULL,
      expected_date TEXT, started_at TEXT NOT NULL, finished_at TEXT,
      status TEXT NOT NULL, error_type TEXT, error_message TEXT,
      snapshot_published INTEGER NOT NULL DEFAULT 0, report TEXT);
    CREATE TABLE IF NOT EXISTS attempts (
      id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
      provider TEXT NOT NULL, series TEXT NOT NULL, attempt_count INTEGER NOT NULL,
      started_at TEXT NOT NULL, finished_at TEXT NOT NULL, retrieved_at TEXT,
      latest_observation_date TEXT, status TEXT NOT NULL, error_type TEXT, error_message TEXT);
    CREATE TABLE IF NOT EXISTS snapshots (
      snapshot_id TEXT PRIMARY KEY, market TEXT NOT NULL, observation_date TEXT NOT NULL,
      published_at TEXT NOT NULL, job_id TEXT NOT NULL REFERENCES jobs(job_id), payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS current_snapshots (
      market TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id));
    CREATE TABLE IF NOT EXISTS scheduler (
      market TEXT PRIMARY KEY, heartbeat_at TEXT NOT NULL, expected_date TEXT NOT NULL,
      expected_run_at TEXT NOT NULL, last_run_at TEXT, last_run_expected_date TEXT);
    CREATE TABLE IF NOT EXISTS alerts (
      id INTEGER PRIMARY KEY, market TEXT NOT NULL, job_id TEXT, action TEXT NOT NULL,
      created_at TEXT NOT NULL, payload TEXT NOT NULL, delivered_at TEXT);
    ''')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def record_attempt(job_id, provider, series, attempt, started_at, status, latest=None, error=None):
    finished = utcnow()
    with database() as db:
        db.execute('INSERT INTO attempts (job_id,provider,series,attempt_count,started_at,finished_at,retrieved_at,latest_observation_date,status,error_type,error_message) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   (job_id, provider, series, attempt, started_at, finished, finished if status == 'SUCCESS' else None, latest, status, type(error).__name__ if error else None, str(error)[:500] if error else None))
    return finished


def publish(job_id, market, payload):
    # The pointer and job success commit together. Readers never see staged data.
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
    snapshot_id = hashlib.sha256((market + encoded).encode()).hexdigest()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT s.observation_date FROM snapshots s JOIN current_snapshots c USING(snapshot_id) WHERE c.market=?', (market,)).fetchone()
        if previous and payload['last_updated'] < previous['observation_date']:
            raise ValueError('Refusing snapshot date regression.')
        db.execute('INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?,?,?)', (snapshot_id, market, payload['last_updated'], utcnow(), job_id, encoded))
        db.execute('INSERT INTO current_snapshots VALUES (?,?) ON CONFLICT(market) DO UPDATE SET snapshot_id=excluded.snapshot_id', (market, snapshot_id))
        db.execute("UPDATE jobs SET status='SUCCESS',finished_at=?,snapshot_published=1,report=? WHERE job_id=?", (utcnow(), encoded, job_id))
    return snapshot_id


def snapshot(market):
    with database() as db:
        row = db.execute('SELECT s.* FROM snapshots s JOIN current_snapshots c USING(snapshot_id) WHERE c.market=?', (market,)).fetchone()
    if not row:
        return None
    if hashlib.sha256((market + row['payload']).encode()).hexdigest() != row['snapshot_id']:
        raise ValueError('Stored snapshot integrity check failed.')
    return {**dict(row), 'payload': json.loads(row['payload'])}


def history(market=None, limit=50):
    with database() as db:
        query = 'SELECT * FROM jobs' + (' WHERE market=?' if market else '') + ' ORDER BY started_at DESC LIMIT ?'
        rows = db.execute(query, (market, limit) if market else (limit,)).fetchall()
        result = []
        for row in rows:
            job = dict(row)
            job['report'] = json.loads(job['report']) if job['report'] else None
            job['attempts'] = [dict(a) for a in db.execute('SELECT * FROM attempts WHERE job_id=? ORDER BY id', (job['job_id'],))]
            result.append(job)
    return result
