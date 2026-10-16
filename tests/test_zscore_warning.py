import numpy as np
import pandas as pd
import pytest

from src.models.zscore_warning import (
    MIN_PERIODS,
    add_zscore_warning,
    latest_zscore_warning,
)


@pytest.fixture
def msi_df():
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2015-01-01", periods=600)
    return pd.DataFrame({"MSI": rng.normal(size=len(dates))}, index=dates)


def test_warmup_rows_are_nan_not_zero(msi_df):
    out = add_zscore_warning(msi_df)

    # shift(1) + min_periods: the first MIN_PERIODS rows have no threshold
    assert out["ZScore_Watch_Threshold"].iloc[:MIN_PERIODS].isna().all()
    assert out["ZScore_Warning"].iloc[:MIN_PERIODS].isna().all()
    assert out["ZScore_Warning"].iloc[MIN_PERIODS:].notna().all()


def test_warning_is_msi_at_or_above_past_80th_percentile(msi_df):
    out = add_zscore_warning(msi_df)

    t = 400
    expected = msi_df["MSI"].iloc[:t].quantile(0.80)
    assert out["ZScore_Watch_Threshold"].iloc[t] == pytest.approx(expected)

    valid = out["ZScore_Warning"].notna()
    np.testing.assert_array_equal(
        out.loc[valid, "ZScore_Warning"].to_numpy(),
        (out.loc[valid, "MSI"] >= out.loc[valid, "ZScore_Watch_Threshold"]).astype(float).to_numpy(),
    )


def test_threshold_uses_no_future_information(msi_df):
    base = add_zscore_warning(msi_df)

    cut = msi_df.index[-50]
    perturbed = msi_df.copy()
    perturbed.loc[cut:, "MSI"] += 5.0
    changed = add_zscore_warning(perturbed)

    before = base.index < cut
    pd.testing.assert_frame_equal(base.loc[before], changed.loc[before])
    # Sanity: the perturbation really changed later warnings.
    assert not base.loc[cut:, "ZScore_Warning"].equals(changed.loc[cut:, "ZScore_Warning"])


def test_watch_threshold_is_below_stress_threshold(msi_df):
    out = add_zscore_warning(msi_df)
    stress_threshold = msi_df["MSI"].shift(1).expanding(min_periods=MIN_PERIODS).quantile(0.90)

    valid = out["ZScore_Watch_Threshold"].notna()
    assert (out.loc[valid, "ZScore_Watch_Threshold"] <= stress_threshold[valid]).all()


def test_warning_rate_is_close_to_one_in_five(msi_df):
    out = add_zscore_warning(msi_df)
    assert 0.12 < out["ZScore_Warning"].mean() < 0.28


def test_korea_column_name():
    dates = pd.bdate_range("2020-01-01", periods=300)
    df = pd.DataFrame({"Korea_MSI": np.linspace(-1, 1, len(dates))}, index=dates)

    out = add_zscore_warning(df, msi_col="Korea_MSI")

    # A steadily rising MSI is always above its past 80th percentile.
    assert (out["ZScore_Warning"].dropna() == 1).all()


def test_missing_column_raises(msi_df):
    with pytest.raises(ValueError, match="Missing MSI column"):
        add_zscore_warning(msi_df, msi_col="Korea_MSI")


def test_missing_msi_gives_nan_warning(msi_df):
    df = msi_df.copy()
    df.iloc[450, 0] = np.nan

    out = add_zscore_warning(df)

    assert np.isnan(out["ZScore_Warning"].iloc[450])


def test_latest_status(msi_df):
    df = msi_df.copy()
    df.iloc[-1, 0] = 10.0
    out = add_zscore_warning(df)

    latest = latest_zscore_warning(out)

    assert latest["date"] == df.index[-1].date().isoformat()
    assert latest["msi"] == pytest.approx(10.0)
    assert latest["warning_active"] is True
