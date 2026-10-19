"""Durable ledger and one-transaction last-known-good publication."""
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from src.config import DATA_DIR


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def root():
    return Path(os.getenv('MARKET_OPERATIONS_DIR', str(DATA_DIR / 'operations')))


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
    from .monitoring import SCHEMA
    db.executescript(SCHEMA)
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


def publish(job_id, market, payload, report=None, *, record_type='RETROSPECTIVE'):
    if 'attribution' in payload:
        from src.explainability.attribution import validate
        validate(payload['attribution'], payload, market)
    # The pointer and job success commit together. Readers never see staged data.
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
    snapshot_id = hashlib.sha256((market + encoded).encode()).hexdigest()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        job = db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
        if not job or job['market'] != market:
            raise ValueError('Publication requires a ledger job for the same market.')
        previous = db.execute('SELECT s.observation_date FROM snapshots s JOIN current_snapshots c USING(snapshot_id) WHERE c.market=?', (market,)).fetchone()
        if previous and payload['last_updated'] < previous['observation_date']:
            raise ValueError('Refusing snapshot date regression.')
        # Identical observations/results reuse the committed snapshot despite new retrieval/job times.
        previous_payload = db.execute('SELECT s.* FROM snapshots s JOIN current_snapshots c USING(snapshot_id) WHERE c.market=?', (market,)).fetchone()
        def content(value):
            value = dict(value)
            for key in ['artifact_directory', 'refresh_job_id', 'model_inference_at', 'data_retrieved_at', 'expected_date_at_refresh']:
                value.pop(key, None)
            value['input_series'] = [{k:v for k,v in item.items() if k not in ['retrieved_at','attempt_count','status']} for item in value.get('input_series',[])]
            return value
        if previous_payload and content(json.loads(previous_payload['payload'])) == content(payload):
            snapshot_id = previous_payload['snapshot_id']
        published_at = utcnow()
        db.execute('INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?,?,?)', (snapshot_id, market, payload['last_updated'], published_at, job_id, encoded))
        # Log the exact snapshot readers receive, including when content deduplication
        # reuses an older snapshot. The new publication still gets its own record.
        from .monitoring import append_publication
        published = db.execute('SELECT payload FROM snapshots WHERE snapshot_id=?', (snapshot_id,)).fetchone()['payload']
        append_publication(db, job, market, snapshot_id, published, published_at,
                           record_type=record_type, refresh_payload=payload)
        db.execute('INSERT INTO current_snapshots VALUES (?,?) ON CONFLICT(market) DO UPDATE SET snapshot_id=excluded.snapshot_id', (market, snapshot_id))
        db.execute("UPDATE jobs SET status='SUCCESS',finished_at=?,snapshot_published=1,report=? WHERE job_id=?", (published_at, json.dumps(report, allow_nan=False) if report is not None else encoded, job_id))
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


def artifact_reference(directory):
    """New immutable snapshots store paths relative to the operations volume."""
    return Path(directory).resolve().relative_to(root().resolve()).as_posix()


def artifact_path(reference):
    """Resolve portable and legacy references without rewriting signed history.

    Old installations stored absolute .../operations/staging/<job-id> paths.
    Only that known layout is rebased; traversal/outside-volume paths are refused.
    """
    base = root().resolve()
    value = Path(reference)
    if value.is_absolute():
        try:
            value = value.relative_to(base)
        except ValueError:
            parts = value.parts
            if len(parts) < 3 or parts[-2] != 'staging':
                raise ValueError('Unknown legacy artifact path.')
            value = Path('staging') / parts[-1]
    resolved = (base / value).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError('Artifact path escapes the operations volume.')
    return resolved
