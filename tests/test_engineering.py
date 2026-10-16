import numpy as np
import pandas as pd
import pytest

from src.features.engineering import FeatureEngineer
from tests.conftest import FEATURE_COLS


def test_feature_matrix_has_17_complete_features(feature_pipeline):
    fm = feature_pipeline.features

    assert all(col in fm.columns for col in FEATURE_COLS)
    assert len(FEATURE_COLS) == 17
    assert not fm[FEATURE_COLS].isna().any().any()
    assert not fm.index.duplicated().any()
    assert fm.index.is_monotonic_increasing


def test_feature_matrix_is_inner_join_with_targets(feature_pipeline):
    fm = feature_pipeline.features
    targets = feature_pipeline.targets

    assert fm.index.isin(targets.index).all()
    for col in ["MSI", "Stress_Threshold", "Is_Stress_Event",
                "Target_1D", "Target_5D", "Target_10D", "Target_20D"]:
        assert col in fm.columns
    pd.testing.assert_series_equal(
        fm["MSI"], targets.loc[fm.index, "MSI"], check_names=False
    )


def test_feature_definitions(feature_pipeline, market_df):
    fm = feature_pipeline.features
    raw = market_df

    np.testing.assert_allclose(
        fm["SPY_1D_Return"].values,
        raw["SPY"].pct_change(1).loc[fm.index].values,
    )
    np.testing.assert_allclose(fm["VIX_Level"].values, raw.loc[fm.index, "VIX"].values)
    np.testing.assert_allclose(
        fm["Credit_Level"].values, raw.loc[fm.index, "BAA_Treasury_Spread"].values
    )
    np.testing.assert_allclose(
        fm["VIX_5D_Change"].values, raw["VIX"].diff(5).loc[fm.index].values
    )

    # Drawdown relative to running peak is never positive.
    assert (fm["SPY_Drawdown"] <= 1e-12).all()

    # Annualised 20D vol: rolling std of daily returns times sqrt(252).
    expected_vol = raw["SPY"].pct_change(1).rolling(20).std() * np.sqrt(252)
    np.testing.assert_allclose(fm["SPY_20D_Vol"].values, expected_vol.loc[fm.index].values)


def test_zscore_features_are_past_only(feature_pipeline, market_df):
    fm = feature_pipeline.features
    vix = market_df["VIX"]
    hist = vix.shift(1)
    expected = (vix - hist.rolling(252, min_periods=60).mean()) / (
        hist.rolling(252, min_periods=60).std() + 1e-8
    )
    np.testing.assert_allclose(fm["VIX_252D_ZScore"].values, expected.loc[fm.index].values)


def test_latest_features_extend_beyond_labelled_matrix(feature_pipeline):
    """Inference features exist for dates whose 10D target is not yet known."""
    latest = pd.read_csv(
        feature_pipeline.dirs.DATA_FEATURES_DIR / "latest_features.csv",
        index_col="Date",
        parse_dates=True,
    )
    fm = feature_pipeline.features

    assert list(latest.columns) == ["SPY", "VIX", "BAA_Treasury_Spread"] + FEATURE_COLS
    assert latest.index.max() >= fm.index.max()
    assert not latest[FEATURE_COLS].isna().any().any()
    # Trailing dates of the labelled matrix carry unknown 10D targets.
    assert fm["Target_10D"].iloc[-10:].isna().all()


def test_saved_matrix_matches_return(feature_pipeline):
    saved = pd.read_csv(
        feature_pipeline.dirs.DATA_FEATURES_DIR / "feature_matrix.csv",
        index_col="Date",
        parse_dates=True,
    )
    assert saved.shape == feature_pipeline.features.shape
    np.testing.assert_allclose(
        saved[FEATURE_COLS].values, feature_pipeline.features[FEATURE_COLS].values
    )


def test_duplicate_dates_in_targets_raise(data_dirs, cleaned_csv):
    from src.features.stress_index import StressIndexCalculator
    from src.features.targets import TargetGenerator

    StressIndexCalculator().calculate_msi()
    targets = TargetGenerator().generate_targets()

    dup = pd.concat([targets, targets.iloc[[100]]]).sort_index()
    dup.to_csv(data_dirs.DATA_FEATURES_DIR / "targets.csv")

    with pytest.raises(ValueError, match="Duplicate dates"):
        FeatureEngineer().generate_features()
