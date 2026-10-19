"""Publication-time audit records. No inference, replay, backfill or outcome fitting."""
import hashlib
import json
import math
import re
from datetime import date, datetime
from uuid import uuid4

from .calendar import expected, series_expected

SERIES = {
    'us': ('SPY', 'VIX', 'DBAA', 'DGS10'),
    'korea': ('KOSPI200', 'VKOSPI', 'Korea_Treasury_3Y', 'Korea_Corporate_AAminus_3Y'),
}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS monitoring_records (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  record_id TEXT UNIQUE NOT NULL,
  market TEXT NOT NULL CHECK(market IN ('us','korea')),
  generated_at TEXT NOT NULL,
  observation_date TEXT NOT NULL,
  record_type TEXT NOT NULL CHECK(record_type IN ('LIVE','RETROSPECTIVE')),
  refresh_job_id TEXT NOT NULL REFERENCES jobs(job_id),
  snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
  payload TEXT NOT NULL,
  record_sha256 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS monitoring_publication_order
  ON monitoring_records(market,record_type,sequence DESC);
CREATE TRIGGER IF NOT EXISTS monitoring_no_update BEFORE UPDATE ON monitoring_records
  BEGIN SELECT RAISE(ABORT,'immutable monitoring record'); END;
CREATE TRIGGER IF NOT EXISTS monitoring_no_delete BEFORE DELETE ON monitoring_records
  BEGIN SELECT RAISE(ABORT,'immutable monitoring record'); END;
CREATE TRIGGER IF NOT EXISTS monitoring_no_replace BEFORE INSERT ON monitoring_records
  WHEN EXISTS (SELECT 1 FROM monitoring_records WHERE record_id=NEW.record_id OR sequence=NEW.sequence)
  BEGIN SELECT RAISE(ABORT,'immutable monitoring record'); END;
CREATE TABLE IF NOT EXISTS monitoring_outcomes (
  outcome_id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES monitoring_records(record_id),
  evaluation_date TEXT NOT NULL,
  evaluation_version TEXT NOT NULL,
  payload TEXT NOT NULL,
  outcome_sha256 TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS monitoring_outcomes_no_update BEFORE UPDATE ON monitoring_outcomes
  BEGIN SELECT RAISE(ABORT,'immutable monitoring outcome'); END;
CREATE TRIGGER IF NOT EXISTS monitoring_outcomes_no_delete BEFORE DELETE ON monitoring_outcomes
  BEGIN SELECT RAISE(ABORT,'immutable monitoring outcome'); END;
CREATE TRIGGER IF NOT EXISTS monitoring_outcomes_no_replace BEFORE INSERT ON monitoring_outcomes
  WHEN EXISTS (SELECT 1 FROM monitoring_outcomes WHERE outcome_id=NEW.outcome_id)
  BEGIN SELECT RAISE(ABORT,'immutable monitoring outcome'); END;
'''


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timezone-aware monitoring timestamp required.')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Timezone-aware monitoring timestamp required.')
    return parsed


def optional_timestamp(value):
    try:
        return timestamp(value).isoformat()
    except ValueError:
        return None


def observation(value):
    return date.fromisoformat(value).isoformat()


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def boolean(value):
    return value if isinstance(value, bool) else None


def digest(value):
    # Unknown provenance stays null; arbitrary strings/paths are never public hashes.
    return value.lower() if isinstance(value, str) and re.fullmatch(r'[a-fA-F0-9]{64}', value) else None


def source_dates(market, payload):
    items = {item['series']: item for item in payload.get('input_series', [])
             if isinstance(item, dict) and item.get('series') in SERIES[market]}
    dates = {}
    for name in SERIES[market]:
        item = items.get(name, {})
        used = item.get('used_observation_date') or item.get('latest_observation_date')
        try:
            used = observation(used)
            # A later source value cannot describe the input used for an earlier origin.
            dates[name] = used if used <= payload['last_updated'] else None
        except (TypeError, ValueError):
            dates[name] = None
    return items, dates


def assess(market, payload, now):
    """Pure dated assessment; never modify the published risk or stored health."""
    items, dates = source_dates(market, payload)
    complete = all(dates.values())
    try:
        due, _ = expected(market, now)
        current = complete and payload.get('source_provenance') == 'provider-validated'
        for name in SERIES[market]:
            item = items.get(name, {})
            try:
                retrieved = timestamp(item.get('retrieved_at'))
                current = current and retrieved <= now and dates[name] >= series_expected(market, name, due)
            except (TypeError, ValueError):
                current = False
        freshness = ('CURRENT' if current else 'STALE') if complete else 'UNAVAILABLE'
    except Exception:
        # Failure to establish the exchange/publication calendar cannot imply CURRENT.
        due, freshness = None, 'UNAVAILABLE'
    risk = number(payload.get('risk_score_10d'))
    msi = number(payload.get('market_stress_index'))
    if risk is None and msi is None:
        status = 'UNAVAILABLE'
    elif (risk is None or msi is None or not complete or
          number(payload.get('stress_threshold')) is None or
          boolean(payload.get('warning_active')) is None or
          boolean(payload.get('is_stress_event')) is None):
        status = 'INCOMPLETE'
    else:
        status = freshness
    return {'status': status, 'freshness_status': freshness,
            'expected_observation_date': due, 'assessed_at': now.isoformat()}


def append_publication(db, job, market, snapshot_id, encoded_snapshot, generated_at, *,
                       record_type, refresh_payload):
    """Called only inside store.publish's transaction; no independent LIVE importer."""
    if market not in SERIES or record_type not in ('LIVE', 'RETROSPECTIVE'):
        raise ValueError('Unknown monitoring market or record type.')
    now = timestamp(generated_at)
    if record_type == 'LIVE':
        inferred = timestamp(refresh_payload.get('model_inference_at'))
        if (job['status'] != 'RUNNING' or job['trigger'] == 'adopt-local' or
                refresh_payload.get('source_provenance') != 'provider-validated' or
                refresh_payload.get('refresh_job_id') != job['job_id'] or
                not timestamp(job['started_at']) <= inferred <= now):
            raise ValueError('LIVE requires fresh inference in the active publication job.')
    payload = json.loads(encoded_snapshot)
    # Verify the established snapshot hash convention, rather than inventing an ID.
    if hashlib.sha256((market + encoded_snapshot).encode()).hexdigest() != snapshot_id:
        raise ValueError('Published monitoring snapshot integrity check failed.')
    _, dates = source_dates(market, payload)
    equity, volatility, *credit = SERIES[market]
    health = assess(market, payload, now)
    record = {
        'record_id': uuid4().hex, 'market': market, 'generated_at': generated_at,
        'observation_date': observation(payload['last_updated']),
        'model_inference_at': optional_timestamp(payload.get('model_inference_at')),
        'risk_score': number(payload.get('risk_score_10d')),
        'operational_warning': boolean(payload.get('warning_active')),
        'operational_warning_threshold': 50.0,
        'msi': number(payload.get('market_stress_index')),
        'msi_stress_threshold': number(payload.get('stress_threshold')),
        'msi_stress_event': boolean(payload.get('is_stress_event')),
        'risk_horizon_trading_days': 10,
        'data_status': health['status'], 'data_freshness_status': health['freshness_status'],
        'expected_observation_date_at_publication': health['expected_observation_date'],
        'equity_observation_date': dates[equity],
        'volatility_observation_date': dates[volatility],
        'credit_observation_date': min(dates[n] for n in credit) if all(dates[n] for n in credit) else None,
        'credit_observation_dates': {name: dates[name] for name in credit},
        'model_sha256': digest(payload.get('model_sha256')),
        'input_snapshot_sha256': hashlib.sha256(encoded_snapshot.encode()).hexdigest(),
        'source_history_sha256': digest(payload.get('source_history_sha256')),
        'refresh_job_id': job['job_id'], 'snapshot_id': snapshot_id,
        'record_type': record_type, 'schema_version': 1,
    }
    # Only explicitly selected public fields are persisted in the API record.
    encoded = json.dumps(record, sort_keys=True, allow_nan=False)
    db.execute('''INSERT INTO monitoring_records
      (record_id,market,generated_at,observation_date,record_type,refresh_job_id,snapshot_id,payload,record_sha256)
      VALUES (?,?,?,?,?,?,?,?,?)''',
      (record['record_id'], market, generated_at, record['observation_date'], record_type,
       job['job_id'], snapshot_id, encoded, hashlib.sha256(encoded.encode()).hexdigest()))


def decode(row):
    if hashlib.sha256(row['payload'].encode()).hexdigest() != row['record_sha256']:
        raise ValueError('Monitoring record integrity check failed.')
    record = json.loads(row['payload'])
    record['publication_sequence'] = row['sequence']
    return record


def history(market, *, record_type='LIVE', limit=50, before_sequence=None):
    from .store import database
    if market not in SERIES or record_type not in ('LIVE', 'RETROSPECTIVE', 'ALL'):
        raise ValueError('Unknown monitoring market or record type.')
    if not 1 <= limit <= 500 or (before_sequence is not None and before_sequence < 1):
        raise ValueError('Invalid monitoring pagination.')
    clauses, args = ['market=?'], [market]
    if record_type != 'ALL':
        clauses.append('record_type=?'); args.append(record_type)
    if before_sequence is not None:
        clauses.append('sequence<?'); args.append(before_sequence)
    with database() as db:
        rows = db.execute('SELECT * FROM monitoring_records WHERE ' + ' AND '.join(clauses) +
                          ' ORDER BY sequence DESC LIMIT ?', (*args, limit + 1)).fetchall()
    records = [decode(row) for row in rows[:limit]]
    return {'market': market, 'record_type': record_type, 'records': records,
            'next_before_sequence': records[-1]['publication_sequence'] if len(rows) > limit else None}


def latest(market, *, record_type='LIVE'):
    from .store import database, utcnow
    records = history(market, record_type=record_type, limit=1)['records']
    record = records[0] if records else None
    now = timestamp(utcnow())
    health = {'status': 'UNAVAILABLE', 'freshness_status': 'UNAVAILABLE',
              'expected_observation_date': None, 'assessed_at': now.isoformat()}
    if record:
        with database() as db:
            row = db.execute('SELECT payload FROM snapshots WHERE snapshot_id=?', (record['snapshot_id'],)).fetchone()
        if hashlib.sha256(row['payload'].encode()).hexdigest() != record['input_snapshot_sha256']:
            raise ValueError('Monitoring snapshot integrity check failed.')
        health = assess(market, json.loads(row['payload']), now)
    return {'market': market, 'record': record, 'current_data_health': health}
