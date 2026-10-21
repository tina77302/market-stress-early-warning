"""Bounded observation-date replay; never a publication or verified PIT forecast.

Run: .venv/bin/python -m src.research.us_retrospective
Existing calculations write only to temporary directories. No refresh, training,
database, download, or publication code is invoked.
"""
import ast
import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path

import exchange_calendars as xcals
import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'data/operations/staging/da92354600a54b5fb68153529ef5cac2/source_history.csv'
MODEL = ROOT / 'models/saved/xgboost_latest.joblib'
MODEL_SHA = '90c51c245ebe62b58f804098a7a7045b60fb64ef83da72d4c9a049cf8d5eeb0d'
SOURCE_SHA = '6c919e24c3bd4126158dcc6275dcc1043dd269ca3a44ac373930cbc8fec2374c'
START, END = '2026-09-17', '2026-10-09'
OUTPUT = ROOT / 'frontend/src/app/components/us-retrospective-observations.json'
AUDIT = ROOT / 'docs/us-retrospective-audit.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def feature_columns():
    # Read the authoritative order without importing API or opening its databases.
    tree = ast.parse((ROOT / 'src/api/main.py').read_text())
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'FEATURE_COLS' for t in node.targets))


def load_source():
    if sha(MODEL) != MODEL_SHA or sha(SOURCE) != SOURCE_SHA:
        raise ValueError('Frozen model or approved source hash differs; replay refused.')
    frame = pd.read_csv(SOURCE, index_col='Date', parse_dates=True)
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError('Source observation dates must be unique and sorted.')
    return frame


def calculate_prefix(source, cutoff):
    """Reuse unchanged US builders on a physical prefix, with scratch-only paths."""
    from src.data import cleaner
    from src.features import engineering, stress_index, targets

    raw = source.loc[:cutoff, ['SPY', 'VIX', 'DBAA', 'DGS10']].copy()
    if pd.Timestamp(cutoff) not in raw.index or not np.isfinite(raw.loc[cutoff]).all():
        raise ValueError('Required source observation is missing; no date substitution permitted.')
    raw['BAA_Treasury_Spread'] = raw['DBAA'] - raw['DGS10']
    with tempfile.TemporaryDirectory(prefix='us-retrospective-') as scratch:
        directory = Path(scratch)
        raw[['SPY', 'VIX', 'BAA_Treasury_Spread']].to_csv(directory / 'raw_market_data.csv')
        # Builders use module constants for output folders as well as instance paths.
        patches = [(cleaner, 'DATA_PROCESSED_DIR'), (engineering, 'DATA_FEATURES_DIR'),
                   (stress_index, 'DATA_FEATURES_DIR'), (targets, 'DATA_FEATURES_DIR')]
        previous = [(module, key, getattr(module, key)) for module, key in patches]
        try:
            for module, key in patches:
                setattr(module, key, directory)
            clean = cleaner.MarketDataCleaner()
            clean.input_path = directory / 'raw_market_data.csv'
            clean.output_path = directory / 'cleaned_market_data.csv'
            msi = stress_index.StressIndexCalculator()
            msi.input_path, msi.output_path = clean.output_path, directory / 'market_stress_index.csv'
            target = targets.TargetGenerator()
            target.input_path, target.output_path = msi.output_path, directory / 'targets.csv'
            features = engineering.FeatureEngineer()
            features.input_path = clean.output_path
            features.target_path, features.output_path = target.output_path, directory / 'feature_matrix.csv'
            with contextlib.redirect_stdout(io.StringIO()):
                clean.clean()
                msi.calculate_msi()
                # Existing feature builder writes independent inference X before
                # its label join. No future label is read by the model below.
                target.generate_targets()
                features.generate_features()
            x = pd.read_csv(directory / 'latest_features.csv', index_col='Date', parse_dates=True)
            values = pd.read_csv(msi.output_path, index_col='Date', parse_dates=True)
            events = pd.read_csv(target.output_path, index_col='Date', parse_dates=True)
        finally:
            for module, key, value in previous:
                setattr(module, key, value)
    if x.index[-1] != pd.Timestamp(cutoff) or values.index[-1] != pd.Timestamp(cutoff):
        raise ValueError('Feature/MSI date does not equal requested observation date.')
    return x, values, events


def generate():
    source = load_source()
    columns = feature_columns()
    model = joblib.load(MODEL)
    if list(model.feature_names_in_) != columns or model.n_features_in_ != 17:
        raise ValueError('Frozen feature ordering mismatch.')
    dates = xcals.get_calendar('XNYS').sessions_in_range(START, END)
    if len(dates) != 17:
        raise ValueError('Approved replay must contain exactly 17 exchange sessions.')
    full_x, full_msi, _ = calculate_prefix(source, END)
    rows, checks = [], []
    for date in dates:
        day = date.strftime('%Y-%m-%d')
        x, msi, events = calculate_prefix(source, day)
        # Each observation is rebuilt without later rows, then compared with
        # the multi-date calculation to detect feature/date look-ahead errors.
        np.testing.assert_allclose(x.loc[date, columns], full_x.loc[date, columns], rtol=0, atol=1e-12)
        np.testing.assert_allclose(msi.loc[date, 'MSI'], full_msi.loc[date, 'MSI'], rtol=0, atol=1e-12)
        if not np.isfinite(x.loc[date, columns]).all():
            raise ValueError('Non-finite inference input.')
        probability = float(model.predict_proba(x.loc[[date], columns])[0, 1])
        if not 0 <= probability <= 1:
            raise ValueError('Invalid probability.')
        rows.append({'date': day, 'score': round(probability * 100, 1),
                     'msi': round(float(msi.loc[date, 'MSI']), 3),
                     'movement': None, 'warning': probability >= .5,
                     'stress': bool(events.loc[date, 'Is_Stress_Event']),
                     'published': None, 'health': None,
                     'basis': 'Retrospective · PIT not verified', 'snapshot_id': None})
        checks.append({'date': day, 'feature_date': x.index[-1].strftime('%Y-%m-%d'),
                       'prefix_matches_full': True,
                       'features': {key: float(x.loc[date, key]) for key in columns},
                       'probability': probability, 'msi_unrounded': float(msi.loc[date, 'MSI'])})
    # Match existing stored calculations, without recalculating or changing them.
    stored_x = pd.read_csv(SOURCE.parent / 'latest_features.csv', index_col='Date', parse_dates=True)
    stored_msi = pd.read_csv(SOURCE.parent / 'market_stress_index.csv', index_col='Date', parse_dates=True)
    np.testing.assert_allclose(full_x.loc[dates, columns], stored_x.loc[dates, columns], rtol=0, atol=1e-12)
    np.testing.assert_allclose(full_msi.loc[dates, 'MSI'], stored_msi.loc[dates, 'MSI'], rtol=0, atol=1e-12)
    prior_x, prior_msi, _ = calculate_prefix(source, '2026-09-16')
    diagnostic = round(float(model.predict_proba(prior_x.loc[['2026-09-16'], columns])[0, 1]) * 100, 1)
    source_spec = json.loads((SOURCE.parent / 'inputs.json').read_text())
    archive = {'market': 'us', 'record_type': 'RETROSPECTIVE', 'pit_verified': False,
               'description': 'Observation-date replay of preserved October 14 inputs; historical publication times and vintages are not verified. Not LIVE, not Historical OOS.',
               'model_sha256': MODEL_SHA, 'source_history_sha256': SOURCE_SHA,
               'source_path': str(SOURCE.relative_to(ROOT)),
               'source_provenance': 'Preserved provider snapshot; historical availability/vintages not verified',
               'source_retrieved_at': {item['series']: item['retrieved_at'] for item in source_spec['series']},
               'feature_columns': columns, 'warning_threshold': 50,
               'unavailable_dates': ['2026-10-12', '2026-10-13', '2026-10-14'],
               'observations': rows}
    audit = {'model_sha256': MODEL_SHA, 'source_history_sha256': SOURCE_SHA,
             'pit_verified': False, 'prefix_checks': checks, 'stored_calculations_match': True,
             'diagnostic_only_2026_09_16': {'frozen_score': diagnostic,
                                          'msi': float(prior_msi.loc['2026-09-16', 'MSI']),
                                          'not_historical_oos': True},
             'missing_sources': {'2026-10-12': ['DBAA', 'DGS10'],
                                 '2026-10-13': ['SPY', 'DBAA', 'DGS10'],
                                 '2026-10-14': ['SPY', 'VIX', 'DBAA', 'DGS10']}}
    if sha(MODEL) != MODEL_SHA or sha(SOURCE) != SOURCE_SHA:
        raise ValueError('Protected input changed during replay.')
    return archive, audit


if __name__ == '__main__':
    archive, audit = generate()
    OUTPUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps(archive['observations'], indent=2))
