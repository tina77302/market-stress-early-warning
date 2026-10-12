"""Isolated staging worker. Existing calculations and API rounding are reused.

No training/evaluation invocation and no writes to live research artifacts.
"""
import contextlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from .validation import validate_features, ValidationFailure


def build(market, directory):
    stage = Path(directory)
    spec = json.loads((stage/'inputs.json').read_text())
    from src.api import main as api
    import hashlib
    model_path = api.MODELS_DIR/'xgboost_latest.joblib' if market=='us' else api.KOREA_MODEL_DIR/'xgboost_10d_latest.joblib'
    original_model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if market == 'us':
        from src.data import cleaner
        from src.features import engineering, stress_index, targets
        cleaner.DATA_RAW_DIR = stage
        cleaner.DATA_PROCESSED_DIR = stage
        engineering.DATA_PROCESSED_DIR = stage
        engineering.DATA_FEATURES_DIR = stage
        stress_index.DATA_PROCESSED_DIR = stage
        stress_index.DATA_FEATURES_DIR = stage
        targets.DATA_FEATURES_DIR = stage
        cleaner.MarketDataCleaner().clean()
        stress_index.StressIndexCalculator().calculate_msi()
        targets.TargetGenerator().generate_targets()
        engineering.FeatureEngineer().generate_features()
        features = pd.read_csv(stage/'latest_features.csv',index_col='Date',parse_dates=True)
        msi = pd.read_csv(stage/'market_stress_index.csv',index_col='Date',parse_dates=True)
        events = pd.read_csv(stage/'targets.csv',index_col='Date',parse_dates=True)
        columns = api.FEATURE_COLS
        api.load_latest_features = lambda: features
        api.load_msi_data = lambda: msi
        validate_features(features,columns,spec['common_date'])
        result = api.calculate_latest_risk()
        date = features.index[-1]
        for name in ['Stress_Threshold','Is_Stress_Event']:
            if date not in events.index or not np.isfinite(float(events.loc[date,name])):
                raise ValidationFailure('Current stress threshold/event is unavailable.')
        result.update(stress_threshold=round(float(events.loc[date,'Stress_Threshold']),3),is_stress_event=bool(events.loc[date,'Is_Stress_Event']))
        model_path = api.MODELS_DIR/'xgboost_latest.joblib'
    else:
        from src.korea import build_korea_features as features_module, build_korea_stress_index as msi_module
        for module in [features_module,msi_module]:
            module.KRX_PATH = str(stage/'krx_indices.csv')
            module.VKOSPI_PATH = str(stage/'vkospi.csv')
            module.CREDIT_PATH = str(stage/'ecos_credit.csv')
        features_module.OUTPUT_PATH = str(stage/'korea_feature_matrix.csv')
        features_module.LATEST_OUTPUT_PATH = str(stage/'korea_latest_features.csv')
        features_module.TARGET_PATH = str(api.KOREA_PROCESSED_DIR/'korea_targets.csv')
        msi_module.OUTPUT_PATH = str(stage/'korea_stress_index.csv')
        msi_module.main()
        features_module.main()
        features = pd.read_csv(stage/'korea_latest_features.csv',index_col='Date',parse_dates=True)
        msi = pd.read_csv(stage/'korea_stress_index.csv',index_col='Date',parse_dates=True)
        columns = api.KOREA_FEATURE_COLS
        api.load_korea_latest_features = lambda: features
        api.load_korea_msi_data = lambda: msi
        validate_features(features,columns,spec['common_date'])
        result = api.calculate_korea_latest_risk()
        model_path = api.KOREA_MODEL_DIR/'xgboost_10d_latest.joblib'
    import hashlib
    spec = json.loads((stage/'inputs.json').read_text())
    validate_features(features,columns,spec['common_date'])
    date = features.index[-1]
    if msi.index.duplicated().any() or date not in msi.index:
        raise ValidationFailure('MSI missing/duplicated at inference date.')
    msi_column = 'MSI' if market=='us' else 'Korea_MSI'
    if not np.isfinite(float(msi.loc[date,msi_column])):
        raise ValidationFailure('MSI is not finite.')
    # Validate unrounded output too (API rounding cannot conceal invalid output).
    import joblib
    model = joblib.load(model_path)
    if getattr(model,'n_features_in_',None) != len(columns):
        raise ValidationFailure('Deployment model feature count differs from existing feature specification.')
    names = getattr(model,'feature_names_in_',None)
    if names is not None and list(names)!=columns:
        raise ValidationFailure('Deployment model feature order differs from existing specification.')
    probability = model.predict_proba(features.loc[[date],columns])
    if probability.shape!=(1,2) or not np.isfinite(probability).all() or (probability<0).any() or (probability>1).any() or not np.allclose(probability.sum(axis=1),1):
        raise ValidationFailure('Invalid deployment model output.')
    if hashlib.sha256(model_path.read_bytes()).hexdigest()!=original_model_hash or result['risk_score_10d']!=round(float(probability[0,1])*100,1):
        raise ValidationFailure('Deployment model changed during inference; snapshot rejected.')
    result.update(warning_threshold=50.0,warning_active=bool(probability[0,1]>=0.5),
                  input_series=spec['series'],common_feature_date=spec['common_date'],
                  model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
                  feature_count=len(columns),source_provenance=spec['provenance'],artifact_directory=str(stage))
    for key in ['market_stress_index','stress_threshold','risk_score_10d']:
        if not np.isfinite(result[key]):
            raise ValidationFailure(f'Final snapshot {key} is not finite.')
    if not 0 <= result['risk_score_10d'] <= 100:
        raise ValidationFailure('Risk score outside 0–100.')
    # Quantitative alert only; dramatic moves remain valid and are published.
    result['anomalies'] = spec.get('anomalies',[])
    (stage/'snapshot.json').write_text(json.dumps(result,allow_nan=False))


if __name__ == '__main__':
    with open(Path(sys.argv[2])/'calculation.log','w') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        build(sys.argv[1],sys.argv[2])
