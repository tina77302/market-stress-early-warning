"""Replay integrity: only temporary builder output, no fit/DB/provider calls."""
import json

import numpy as np
import pandas as pd
import pytest

from src.research import us_retrospective as replay


@pytest.fixture(scope='module')
def regenerated():
    return replay.generate()


def test_committed_archive_is_reproducible_and_never_claims_publication(regenerated):
    archive, audit = regenerated
    assert archive == json.loads(replay.OUTPUT.read_text())
    assert audit == json.loads(replay.AUDIT.read_text())
    rows = archive['observations']
    assert len(rows) == 17
    assert rows[0]['date'] == '2026-09-17'
    assert rows[-1]['date'] == '2026-10-09'
    assert archive['record_type'] == 'RETROSPECTIVE'
    assert archive['pit_verified'] is False
    assert all(r['published'] is None and r['snapshot_id'] is None and r['health'] is None for r in rows)
    assert all(r['basis'] == 'Retrospective · PIT not verified' for r in rows)
    assert not set(archive['unavailable_dates']) & {r['date'] for r in rows}
    assert archive['model_sha256'] == replay.sha(replay.MODEL)
    assert archive['source_history_sha256'] == replay.sha(replay.SOURCE)
    for row, check in zip(rows, audit['prefix_checks'], strict=True):
        assert row['date'] == check['feature_date']
        assert check['prefix_matches_full']
        assert row['warning'] == (check['probability'] >= .5)
        assert row['score'] == round(check['probability'] * 100, 1)
        assert row['msi'] == round(check['msi_unrounded'], 3)


def test_later_source_values_do_not_change_a_prefix_and_missing_inputs_fail_closed():
    original = replay.load_source()
    changed = original.copy()
    changed.loc['2026-09-18':] = 9999
    a, ma, _ = replay.calculate_prefix(original, '2026-09-17')
    b, mb, _ = replay.calculate_prefix(changed, '2026-09-17')
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(ma, mb)
    for day in ['2026-10-12', '2026-10-13', '2026-10-14']:
        with pytest.raises(ValueError, match='missing'):
            replay.calculate_prefix(original, day)
    changed = original.copy()
    changed.loc['2026-09-17', 'VIX'] = np.nan
    with pytest.raises(ValueError, match='missing'):
        replay.calculate_prefix(changed, '2026-09-17')


def test_unapproved_source_or_model_hash_is_rejected(monkeypatch):
    monkeypatch.setattr(replay, 'SOURCE_SHA', '0' * 64)
    with pytest.raises(ValueError, match='hash differs'):
        replay.load_source()


def test_frozen_boundary_matches_existing_snapshot_and_oos_inputs(regenerated):
    archive, audit = regenerated
    snapshot = json.loads((replay.SOURCE.parent / 'snapshot.json').read_text())
    assert archive['observations'][-1]['score'] == snapshot['risk_score_10d']
    assert archive['observations'][-1]['msi'] == snapshot['market_stress_index']
    source = replay.load_source()
    oos = pd.read_csv(replay.ROOT / 'data/processed/oos_predictions.csv', index_col='Date')
    endpoint = oos.loc['2026-09-16']
    assert endpoint['SPY'] == source.loc['2026-09-16', 'SPY']
    assert endpoint['VIX'] == source.loc['2026-09-16', 'VIX']
    assert endpoint['BAA_Treasury_Spread'] == pytest.approx(
        source.loc['2026-09-16', 'DBAA'] - source.loc['2026-09-16', 'DGS10'])
    assert audit['diagnostic_only_2026_09_16']['msi'] == pytest.approx(endpoint['MSI'], abs=1e-8)
