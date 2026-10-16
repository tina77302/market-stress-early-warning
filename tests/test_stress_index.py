import numpy as np
import pandas as pd

from tests.conftest import STRESS_START, STRESS_LEN
from src.features.stress_index import StressIndexCalculator


def _past_only_z(series, window=252):
    hist = series.shift(1)
    mean = hist.rolling(window, min_periods=window // 2).mean()
    std = hist.rolling(window, min_periods=window // 2).std()
    return (series - mean) / (std + 1e-8)


def test_msi_is_equal_weighted_mean_of_past_only_zscores(cleaned_csv, market_df):
    out = StressIndexCalculator().calculate_msi()

    z_eq = _past_only_z(-market_df["SPY"].pct_change(21))
    z_vix = _past_only_z(market_df["VIX"])
    z_cr = _past_only_z(market_df["BAA_Treasury_Spread"])
    expected = ((z_eq + z_vix + z_cr) / 3.0).dropna()

    assert list(out.columns) == ["SPY", "VIX", "BAA_Treasury_Spread", "MSI"]
    pd.testing.assert_index_equal(out.index, expected.index, check_names=False)
    np.testing.assert_allclose(out["MSI"].values, expected.values, rtol=1e-10)


def test_warmup_rows_dropped_and_no_nan(cleaned_csv, market_df):
    out = StressIndexCalculator().calculate_msi()

    assert len(out) < len(market_df)
    assert out["MSI"].notna().all()
    assert out.index.is_monotonic_increasing


def test_msi_uses_no_future_information(data_dirs, market_df):
    """Perturbing the future must not change any earlier MSI value."""
    path = data_dirs.DATA_PROCESSED_DIR / "cleaned_market_data.csv"

    market_df.to_csv(path)
    base = StressIndexCalculator().calculate_msi()

    perturbed = market_df.copy()
    cut = perturbed.index[-60]
    perturbed.loc[cut:, "VIX"] *= 3.0
    perturbed.loc[cut:, "SPY"] *= 0.7
    perturbed.loc[cut:, "BAA_Treasury_Spread"] += 2.0
    perturbed.to_csv(path)
    changed = StressIndexCalculator().calculate_msi()

    before = base.index[base.index < cut]
    np.testing.assert_allclose(
        base.loc[before, "MSI"].values,
        changed.loc[before, "MSI"].values,
    )
    # Sanity: the perturbation really moved the later values.
    assert not np.allclose(
        base.loc[cut:, "MSI"].values, changed.loc[cut:, "MSI"].values
    )


def test_stress_episode_raises_msi(cleaned_csv, market_df):
    """The injected stress window should score above the normal period."""
    out = StressIndexCalculator().calculate_msi()

    stress_idx = market_df.index[STRESS_START:STRESS_START + STRESS_LEN]
    calm_idx = market_df.index[STRESS_START - 300:STRESS_START - 100]

    assert out.loc[stress_idx, "MSI"].mean() > out.loc[calm_idx, "MSI"].mean() + 1.0


def test_output_file_matches_return(cleaned_csv, data_dirs):
    out = StressIndexCalculator().calculate_msi()
    saved = pd.read_csv(
        data_dirs.DATA_FEATURES_DIR / "market_stress_index.csv",
        index_col="Date",
        parse_dates=True,
    )
    pd.testing.assert_frame_equal(saved, out, check_freq=False)
