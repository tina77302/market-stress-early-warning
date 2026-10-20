"""Publication ledger invariants. All databases are temporary; no real refreshes."""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.monitoring import router
from src.operations import monitoring, store

NOW = datetime(2026, 10, 16, 7, 58, 51, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('MARKET_OPERATIONS_DIR', str(tmp_path / 'operations'))
    monkeypatch.setattr(store, 'utcnow', lambda: NOW.isoformat())
    monkeypatch.setattr(monitoring, 'expected', lambda market, now: ('2026-10-15', '2026-10-15T12:30:00+00:00'))


def job(market='korea', trigger='manual'):
    jid = uuid4().hex
    with store.database() as db:
        db.execute("INSERT INTO jobs (job_id,market,trigger,started_at,status) VALUES (?,?,?,?,'RUNNING')",
                   (jid, market, trigger, (NOW - timedelta(seconds=2)).isoformat()))
    return jid


def payload(jid, market='korea', date='2026-10-15', score=40.5):
    return {'last_updated': date, 'risk_score_10d': score, 'warning_active': False,
            'market_stress_index': 1.049, 'stress_threshold': 1.116, 'is_stress_event': False,
            'warning_threshold': 50.0, 'source_provenance': 'provider-validated',
            'model_inference_at': (NOW - timedelta(seconds=1)).isoformat(),
            'refresh_job_id': jid, 'model_sha256': 'a' * 64, 'source_history_sha256': 'b' * 64,
            'input_series': [{'series': name, 'used_observation_date': date,
                              'latest_observation_date': date, 'retrieved_at': (NOW - timedelta(minutes=1)).isoformat()}
                             for name in monitoring.SERIES[market]]}


def publish(market='korea', record_type='LIVE', **kwargs):
    jid = job(market)
    value = payload(jid, market, **kwargs)
    sid = store.publish(jid, market, value, record_type=record_type)
    return sid, value


def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize('market', ['us', 'korea'])
def test_publication_records_exact_outputs_and_hashes(market):
    sid, value = publish(market)
    record = monitoring.latest(market)['record']
    assert record['snapshot_id'] == sid
    assert record['risk_score'] == value['risk_score_10d']
    assert record['operational_warning'] is value['warning_active']
    assert record['msi'] == value['market_stress_index']
    assert record['msi_stress_event'] is value['is_stress_event']
    assert record['msi_stress_threshold'] == value['stress_threshold']
    assert record['operational_warning_threshold'] == 50.0
    assert record['risk_horizon_trading_days'] == 10
    assert record['model_sha256'] == value['model_sha256']
    assert record['source_history_sha256'] == value['source_history_sha256']
    encoded = json.dumps(value, sort_keys=True, allow_nan=False)
    assert record['input_snapshot_sha256'] == hashlib.sha256(encoded.encode()).hexdigest()
    assert record['record_type'] == 'LIVE'
    assert record['data_status'] == 'CURRENT'
    assert not any('watch' in key.lower() for key in record)


def test_repeat_same_observation_and_dedup_snapshot_append(monkeypatch):
    sid, value = publish()
    first = monitoring.latest('korea')['record']
    monkeypatch.setattr(store, 'utcnow', lambda: (NOW + timedelta(minutes=1)).isoformat())
    sid2, _ = publish()
    records = monitoring.history('korea')['records']
    assert sid2 == sid  # existing content deduplication remains unchanged
    assert len(records) == 2
    assert records[0]['record_id'] != first['record_id']
    assert records[0]['generated_at'] != first['generated_at']
    assert records[1] == first
    assert records[0]['model_inference_at'] == first['model_inference_at']
    assert records[0]['input_snapshot_sha256'] == first['input_snapshot_sha256']
    with store.database() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 1


def test_source_revision_and_new_model_preserve_old_publication():
    _, _ = publish()
    old = monitoring.latest('korea')['record']
    jid = job(); value = payload(jid, score=61.2)
    value.update(model_sha256='c' * 64, source_history_sha256='d' * 64, warning_active=True)
    store.publish(jid, 'korea', value, record_type='LIVE')
    records = monitoring.history('korea')['records']
    assert records[1] == old
    assert records[0]['risk_score'] == 61.2 and records[0]['operational_warning'] is True
    assert records[0]['model_sha256'] != records[1]['model_sha256']


def test_generated_observed_inferred_are_separate():
    publish()
    record = monitoring.latest('korea')['record']
    assert record['observation_date'] == '2026-10-15'
    assert record['generated_at'] == '2026-10-16T07:58:51+00:00'
    assert record['model_inference_at'] == '2026-10-16T07:58:50+00:00'
    assert datetime.fromisoformat(record['generated_at']).utcoffset() is not None


@pytest.mark.parametrize('statement', [
    "UPDATE monitoring_records SET record_type='LIVE'",
    'DELETE FROM monitoring_records',
    'INSERT OR REPLACE INTO monitoring_records SELECT * FROM monitoring_records',
])
def test_sql_immutability_including_replacement(statement):
    publish(record_type='RETROSPECTIVE')
    with pytest.raises(sqlite3.IntegrityError, match='immutable'):
        with store.database() as db:
            db.execute(statement)
    assert len(monitoring.history('korea', record_type='RETROSPECTIVE')['records']) == 1
    assert monitoring.latest('korea')['record'] is None


def test_no_migration_backfill_or_read_side_live_records():
    # Mimics an existing pre-feature DB: initializing schema alone creates no forecasts.
    jid = job()
    value = payload(jid)
    encoded = json.dumps(value, sort_keys=True, allow_nan=False)
    sid = hashlib.sha256(('korea' + encoded).encode()).hexdigest()
    with store.database() as db:
        db.execute('INSERT INTO snapshots VALUES (?,?,?,?,?,?)',
                   (sid, 'korea', value['last_updated'], NOW.isoformat(), jid, encoded))
        assert db.execute('SELECT COUNT(*) FROM monitoring_records').fetchone()[0] == 0
    for _ in range(2):
        assert client().get('/api/monitoring/latest?market=korea').json()['record'] is None
    publish(record_type='RETROSPECTIVE')
    assert monitoring.latest('korea')['record'] is None
    assert client().get('/api/monitoring/history?market=korea').json()['records'] == []


@pytest.mark.parametrize('change', ['old_inference', 'naive', 'wrong_job', 'cache', 'completed_job', 'adopt_local'])
def test_live_requires_new_active_refresh(change):
    jid = job(trigger='adopt-local' if change == 'adopt_local' else 'manual'); value = payload(jid)
    if change == 'old_inference': value['model_inference_at'] = '2026-10-15T07:58:50+00:00'
    if change == 'naive': value['model_inference_at'] = '2026-10-16T07:58:50'
    if change == 'wrong_job': value['refresh_job_id'] = 'other'
    if change == 'cache': value['source_provenance'] = 'legacy-cache'
    if change == 'completed_job':
        with store.database() as db: db.execute("UPDATE jobs SET status='SUCCESS' WHERE job_id=?", (jid,))
    with pytest.raises(ValueError): store.publish(jid, 'korea', value, record_type='LIVE')
    with store.database() as db:
        assert db.execute('SELECT COUNT(*) FROM monitoring_records').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0


def test_default_publication_is_retrospective_and_null_provenance_safe():
    jid = job(); value = payload(jid)
    value.update(model_sha256=None, source_history_sha256='not-a-hash/internal/path')
    store.publish(jid, 'korea', value)
    record = monitoring.latest('korea', record_type='RETROSPECTIVE')['record']
    assert record['model_sha256'] is None and record['source_history_sha256'] is None
    assert record['input_snapshot_sha256'] is not None
    assert monitoring.latest('korea')['record'] is None


def test_latest_uses_publication_order_not_observation_date():
    # Explicit retrospective fixture import bypasses production's date-regression guard.
    # This tests API ordering without weakening that existing guard.
    publish(record_type='RETROSPECTIVE')
    jid = job(); value = payload(jid, date='2026-10-12')
    encoded = json.dumps(value, sort_keys=True, allow_nan=False)
    sid = hashlib.sha256(('korea' + encoded).encode()).hexdigest()
    with store.database() as db:
        db.execute('INSERT INTO snapshots VALUES (?,?,?,?,?,?)',
                   (sid, 'korea', value['last_updated'], NOW.isoformat(), jid, encoded))
        row = db.execute('SELECT * FROM jobs WHERE job_id=?', (jid,)).fetchone()
        monitoring.append_publication(db, row, 'korea', sid, encoded, NOW.isoformat(),
                                      record_type='RETROSPECTIVE', refresh_payload=value)
    records = monitoring.history('korea', record_type='RETROSPECTIVE')['records']
    assert records[0]['observation_date'] == '2026-10-12'
    assert monitoring.latest('korea', record_type='RETROSPECTIVE')['record'] == records[0]


def test_stale_read_does_not_republish_or_relabel(monkeypatch):
    publish()
    original = monitoring.latest('korea')['record']
    monkeypatch.setattr(monitoring, 'expected', lambda market, now: ('2026-10-19', 'deadline'))
    monkeypatch.setattr(store, 'utcnow', lambda: (NOW + timedelta(days=4)).isoformat())
    result = client().get('/api/monitoring/latest?market=korea').json()
    assert result['record'] == original
    assert result['record']['data_status'] == 'CURRENT'
    assert result['current_data_health']['status'] == 'STALE'
    assert len(monitoring.history('korea')['records']) == 1


@pytest.mark.parametrize('warning', [True, False])
@pytest.mark.parametrize('stale', [True, False])
def test_risk_and_health_are_independent(warning, stale):
    jid = job(); value = payload(jid, date='2026-10-14' if stale else '2026-10-15')
    value.update(warning_active=warning, risk_score_10d=60.0 if warning else 40.5)
    store.publish(jid, 'korea', value, record_type='LIVE')
    record = monitoring.latest('korea')['record']
    assert record['data_status'] == ('STALE' if stale else 'CURRENT')
    assert record['operational_warning'] is warning


def test_display_rounding_does_not_recompute_operational_warning():
    jid = job(); value = payload(jid, score=50.0)  # e.g. raw probability .4996
    value['warning_active'] = False
    store.publish(jid, 'korea', value, record_type='LIVE')
    record = monitoring.latest('korea')['record']
    assert record['risk_score'] == 50.0 and record['operational_warning'] is False


def test_health_missing_channels_calendar_and_outputs(monkeypatch):
    jid = job(); value = payload(jid)
    value['input_series'] = value['input_series'][:1]
    store.publish(jid, 'korea', value)
    record = monitoring.latest('korea', record_type='RETROSPECTIVE')['record']
    assert record['data_status'] == 'INCOMPLETE'
    assert record['credit_observation_date'] is None
    value.update(risk_score_10d=None, market_stress_index=None)
    assert monitoring.assess('korea', value, NOW)['status'] == 'UNAVAILABLE'
    monkeypatch.setattr(monitoring, 'expected', lambda *args: (_ for _ in ()).throw(ValueError('no calendar')))
    assert monitoring.assess('korea', payload(jid), NOW)['status'] == 'UNAVAILABLE'


def test_history_ties_pagination_filters_and_validation():
    for market in ['us', 'korea', 'korea', 'korea']: publish(market)
    publish(record_type='RETROSPECTIVE')
    api = client(); url = '/api/monitoring/history?market=korea&limit=2'
    first = api.get(url).json()
    second = api.get(url + '&before_sequence=' + str(first['next_before_sequence'])).json()
    records = first['records'] + second['records']
    assert len(records) == 3 and len({r['record_id'] for r in records}) == 3
    assert [r['publication_sequence'] for r in records] == sorted([r['publication_sequence'] for r in records], reverse=True)
    assert second['next_before_sequence'] is None
    assert len(api.get('/api/monitoring/history?market=korea&record_type=ALL').json()['records']) == 4
    for query in ['market=other', 'market=korea&limit=0', 'market=korea&limit=501', 'market=korea&before_sequence=0', 'market=korea&record_type=REPLAY']:
        assert api.get('/api/monitoring/history?' + query).status_code == 422
    assert api.post('/api/monitoring/history?market=korea', json={}).status_code == 405


def test_api_has_no_secrets_or_filesystem_paths():
    jid = job(); value = payload(jid)
    value.update(artifact_directory='/private/secret/path', api_key='secret-key',
                 common_feature_date=value['last_updated'], feature_count=17)
    value['attribution'] = {
        'date': value['last_updated'], 'observation_date': value['last_updated'],
        'common_feature_date': value['last_updated'], 'model': 'XGBoost', 'market': 'korea',
        'model_sha256': value['model_sha256'], 'feature_count': 17,
        'source_provenance': value['source_provenance'], 'private': 'secret-token',
        'top_drivers': [{'shap_value': .2, 'feature_value': 1.0}],
    }
    value['input_series'][0]['provider'] = '/internal/provider/path'
    store.publish(jid, 'korea', value, record_type='LIVE')
    response = client().get('/api/monitoring/history?market=korea').text
    for forbidden in ['/private/', '/internal/', 'secret-token', 'secret-key', 'artifact_directory', 'attribution']:
        assert forbidden not in response


def test_ledger_failure_rolls_back_snapshot_pointer_and_job():
    sid, _ = publish()
    jid = job(); value = payload(jid, score=65.0)
    with store.database() as db:
        db.execute("CREATE TRIGGER fail_monitoring BEFORE INSERT ON monitoring_records BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
    with pytest.raises(sqlite3.IntegrityError): store.publish(jid, 'korea', value, record_type='LIVE')
    assert store.snapshot('korea')['snapshot_id'] == sid
    assert len(monitoring.history('korea')['records']) == 1
    with store.database() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 1
        assert db.execute('SELECT status FROM jobs WHERE job_id=?', (jid,)).fetchone()[0] == 'RUNNING'


def test_pointer_failure_rolls_back_monitoring():
    publish()
    with store.database() as db:
        db.execute("CREATE TRIGGER fail_pointer BEFORE UPDATE ON current_snapshots BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
    jid = job()
    with pytest.raises(sqlite3.IntegrityError): store.publish(jid, 'korea', payload(jid, score=65), record_type='LIVE')
    assert len(monitoring.history('korea')['records']) == 1


def test_outcomes_are_separate_immutable_and_empty():
    publish()
    rid = monitoring.latest('korea')['record']['record_id']
    with store.database() as db:
        assert db.execute('SELECT COUNT(*) FROM monitoring_outcomes').fetchone()[0] == 0
        # Schema-only fixture, not a fabricated actual outcome/evaluation.
        db.execute('INSERT INTO monitoring_outcomes VALUES (?,?,?,?,?,?)',
                   ('fixture', rid, '2026-11-01', 'fixture-only', '{}', hashlib.sha256(b'{}').hexdigest()))
    for sql in ['UPDATE monitoring_outcomes SET payload=\'{}\'', 'DELETE FROM monitoring_outcomes',
                'INSERT OR REPLACE INTO monitoring_outcomes SELECT * FROM monitoring_outcomes']:
        with pytest.raises(sqlite3.IntegrityError):
            with store.database() as db: db.execute(sql)
    assert monitoring.latest('korea')['record']['record_id'] == rid


@pytest.mark.parametrize('record_type', ['LIVE', 'RETROSPECTIVE'])
def test_publication_retry_returns_original_without_second_record(record_type):
    jid = job()
    value = payload(jid)
    first = store.publish(jid, 'korea', value, record_type=record_type)
    second = store.publish(jid, 'korea', value, record_type=record_type)
    assert second == first
    assert len(monitoring.history('korea', record_type='ALL')['records']) == 1
    with pytest.raises(ValueError, match='conflicts'):
        store.publish(jid, 'korea', {**value, 'risk_score_10d': 90.0}, record_type=record_type)
    with pytest.raises(ValueError, match='conflicts'):
        store.publish(jid, 'korea', value,
                      record_type='RETROSPECTIVE' if record_type == 'LIVE' else 'LIVE')
