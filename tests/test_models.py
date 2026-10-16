import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

import src.models.walk_forward as wf_module
from src.models.logistic import build_logistic_model
from src.models.xgboost_model import build_xgboost_model
from src.models.walk_forward import WalkForwardValidator
from src.models.multi_horizon_validation import MultiHorizonValidator, HORIZONS
from tests.conftest import FEATURE_COLS, STRESS_START, STRESS_LEN


# --------------------------------------------------------------------------
# Model builders
# --------------------------------------------------------------------------

def _toy_xy(n=200, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, 17)), columns=FEATURE_COLS)
    y = pd.Series((X["VIX_Level"] + rng.normal(0, 0.5, n) > 0.5).astype(int))
    return X, y


@pytest.mark.parametrize("builder", [build_logistic_model, build_xgboost_model])
def test_builders_return_scaled_pipeline(builder):
    model = builder()
    assert isinstance(model, Pipeline)
    assert [name for name, _ in model.steps] == ["scaler", "classifier"]

    X, y = _toy_xy()
    model.fit(X, y)
    proba = model.predict_proba(X)

    assert proba.shape == (len(X), 2)
    np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-6)
    assert ((proba >= 0) & (proba <= 1)).all()


def test_xgboost_scale_pos_weight_passthrough():
    model = build_xgboost_model(scale_pos_weight=4.5)
    assert model.named_steps["classifier"].get_params()["scale_pos_weight"] == 4.5


def test_logistic_is_class_balanced():
    clf = build_logistic_model().named_steps["classifier"]
    assert clf.get_params()["class_weight"] == "balanced"


# --------------------------------------------------------------------------
# Walk-forward validation
# --------------------------------------------------------------------------

class _RecordingModel:
    """Stand-in estimator that records every (train, test) index it sees."""

    calls = []

    def __init__(self, *args, **kwargs):
        self.train_index = None

    def fit(self, X, y):
        self.train_index = X.index
        return self

    def predict_proba(self, X):
        type(self).calls.append((self.train_index, X.index))
        p = np.full(len(X), 0.3)
        return np.column_stack([1 - p, p])


def test_walk_forward_respects_embargo_and_expands(feature_pipeline, monkeypatch):
    _RecordingModel.calls = []
    monkeypatch.setattr(wf_module, "build_logistic_model", lambda: _RecordingModel())
    monkeypatch.setattr(
        wf_module, "build_xgboost_model", lambda scale_pos_weight=1.0: _RecordingModel()
    )

    validator = WalkForwardValidator(
        initial_train_years=1, step_months=1, embargo_days=10
    )
    out = validator.run_validation()

    fm = pd.read_csv(
        validator.input_path, index_col="Date", parse_dates=True
    ).sort_index()
    # Rows with an unknown 10D label are excluded before validation.
    fm = fm.dropna(subset=["Target_10D"])
    pos = {d: i for i, d in enumerate(fm.index)}

    # Two models per fold -> an even number of recorded calls.
    assert _RecordingModel.calls and len(_RecordingModel.calls) % 2 == 0

    folds = _RecordingModel.calls[::2]
    prev_test_start = None
    for train_idx, test_idx in folds:
        train_end_pos = pos[train_idx[-1]]
        test_start_pos = pos[test_idx[0]]

        # Gap between last training row and first test row covers the embargo.
        assert test_start_pos - train_end_pos >= 10
        # Training always starts at the first observation (expanding window).
        assert train_idx[0] == fm.index[0]
        # Test blocks are contiguous and strictly chronological.
        assert test_idx.is_monotonic_increasing
        if prev_test_start is not None:
            assert test_start_pos > prev_test_start
        prev_test_start = test_start_pos

    # First test block starts exactly at min_train_size.
    assert pos[folds[0][1][0]] == validator.min_train_size
    # Every row from min_train_size onward received an OOS prediction.
    assert len(out) == len(fm) - validator.min_train_size
    assert out.index[0] == fm.index[validator.min_train_size]


@pytest.mark.slow
def test_walk_forward_end_to_end(feature_pipeline, market_df):
    validator = WalkForwardValidator(
        initial_train_years=1, step_months=3, embargo_days=10
    )
    out = validator.run_validation()

    assert list(out.columns) == [
        "Actual_Target", "MSI", "SPY", "VIX", "BAA_Treasury_Spread",
        "Prob_Logistic", "Prob_XGBoost",
    ]
    probs = out[["Prob_Logistic", "Prob_XGBoost"]]
    assert ((probs >= 0) & (probs <= 1)).all().all()
    assert out["Actual_Target"].isin([0, 1]).all()
    assert out["Prob_Logistic"].std() > 0 and out["Prob_XGBoost"].std() > 0

    dirs = feature_pipeline.dirs
    assert (dirs.DATA_PROCESSED_DIR / "oos_predictions.csv").exists()
    assert (dirs.MODELS_DIR / "logistic_latest.joblib").exists()
    assert (dirs.MODELS_DIR / "xgboost_latest.joblib").exists()

    # The injected stress episode should receive elevated scores.
    raw_index = market_df.index
    stress_dates = out.index.intersection(raw_index[STRESS_START:STRESS_START + STRESS_LEN])
    assert len(stress_dates) > 0
    stress = out.loc[stress_dates, "Prob_XGBoost"]
    calm = out.iloc[-60:]["Prob_XGBoost"]
    assert stress.mean() > calm.mean()


def test_walk_forward_missing_feature_raises(feature_pipeline):
    path = feature_pipeline.dirs.DATA_FEATURES_DIR / "feature_matrix.csv"
    fm = pd.read_csv(path, index_col="Date", parse_dates=True)
    fm.drop(columns=["VIX_252D_ZScore"]).to_csv(path)

    with pytest.raises(ValueError, match="VIX_252D_ZScore"):
        WalkForwardValidator(initial_train_years=1).run_validation()


# --------------------------------------------------------------------------
# Multi-horizon validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("horizon", HORIZONS)
def test_prepare_horizon_data_drops_unknown_labels_and_sets_purge(feature_pipeline, horizon):
    fm = feature_pipeline.features
    hdf, target_col, purge = MultiHorizonValidator().prepare_horizon_data(fm, horizon)

    assert target_col == f"Target_{horizon}D"
    assert purge == horizon
    assert len(hdf) == len(fm) - horizon
    assert hdf[target_col].notna().all()
    assert hdf[target_col].dtype.kind == "i"


def test_prepare_horizon_data_missing_target_raises(feature_pipeline):
    fm = feature_pipeline.features.drop(columns=["Target_20D"])
    with pytest.raises(ValueError, match="Target_20D"):
        MultiHorizonValidator().prepare_horizon_data(fm, 20)


def test_multi_horizon_run_and_metrics(feature_pipeline):
    fm = feature_pipeline.features
    validator = MultiHorizonValidator(initial_train_years=1, step_months=6)

    oos = validator.run_horizon(fm, 5)
    assert len(oos) == len(fm) - 5 - validator.min_train_size
    assert oos[["Prob_Logistic", "Prob_XGBoost"]].notna().all().all()

    metrics = validator.calculate_metrics(oos, 5)
    assert list(metrics["Model"]) == ["Logistic", "XGBoost"]
    assert (metrics["Horizon"] == "5D").all()
    assert (metrics["OOS_Observations"] == len(oos)).all()
    assert metrics["ROC_AUC"].between(0, 1).all()
    assert metrics["PR_AUC"].between(0, 1).all()
    assert metrics["Brier"].between(0, 1).all()
