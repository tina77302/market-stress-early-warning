"""Single-observation TreeSHAP using the frozen deployment pipeline.

Uses XGBoost's exact TreeSHAP implementation (raw model margin), the same
scaled representation as the existing offline SHAP analyses.
"""
import hashlib
import numpy as np
import pandas as pd
from xgboost import DMatrix


def explain(model, row, *, market, model_sha256, provenance):
    if len(row) != 1 or not np.isfinite(row.to_numpy()).all():
        raise ValueError('Attribution requires one finite validated feature row.')
    scaled = pd.DataFrame(model.named_steps['scaler'].transform(row),
                          index=row.index, columns=row.columns)
    booster = model.named_steps['classifier'].get_booster()
    matrix = DMatrix(scaled)
    contributions = np.asarray(booster.predict(matrix, pred_contribs=True, approx_contribs=False))
    margin = booster.predict(matrix, output_margin=True)
    if contributions.shape != (1, len(row.columns)+1) or not np.isfinite(contributions).all():
        raise ValueError('Invalid TreeSHAP contribution matrix.')
    if not np.allclose(contributions.sum(axis=1), margin, rtol=1e-5, atol=1e-5):
        raise ValueError('TreeSHAP contributions do not reconstruct model margin.')
    values = contributions[0, :-1]
    date = row.index[0].strftime('%Y-%m-%d')
    return {'date': date, 'observation_date': date, 'common_feature_date': date,
            'market': market, 'model': 'XGBoost', 'model_sha256': model_sha256,
            'source_provenance': provenance, 'feature_count': len(row.columns),
            'feature_row_sha256': hashlib.sha256(row.to_csv().encode()).hexdigest(),
            'output_space': 'raw_margin', 'base_value': float(contributions[0, -1]),
            'top_drivers': [
                {'feature': row.columns[i], 'feature_value': float(row.iloc[0, i]),
                 'shap_value': float(values[i]),
                 'direction': 'risk_up' if values[i] > 0 else 'risk_down'}
                for i in np.argsort(-np.abs(values))[:8]],
            'interpretation_note': 'SHAP values explain model output; they are not causal effects or probability-point changes.'}


def validate(attribution, snapshot, market):
    date = snapshot['last_updated']
    if any(attribution.get(key) != date for key in ('date', 'observation_date', 'common_feature_date')) or snapshot.get('common_feature_date') != date:
        raise ValueError('SHAP observation date differs from validated snapshot.')
    if attribution.get('model') != 'XGBoost' or attribution.get('market') != market or not snapshot.get('model_sha256') or attribution.get('model_sha256') != snapshot['model_sha256']:
        raise ValueError('SHAP model identity differs from validated snapshot.')
    if attribution.get('feature_count') != snapshot.get('feature_count') or attribution.get('source_provenance') != snapshot.get('source_provenance'):
        raise ValueError('SHAP provenance differs from validated snapshot.')
    drivers = attribution.get('top_drivers', [])
    if not drivers or any(not np.isfinite(d['shap_value']) or not np.isfinite(d['feature_value']) for d in drivers):
        raise ValueError('Invalid SHAP drivers.')
