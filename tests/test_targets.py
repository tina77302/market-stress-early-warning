import numpy as np
import pandas as pd
import pytest

from tests.conftest import STRESS_START, STRESS_LEN
from src.config import STRESS_QUANTILE_THRESHOLD
from src.features.stress_index import StressIndexCalculator
from src.features.targets import TargetGenerator


@pytest.fixture
def targets(cleaned_csv):
    msi = StressIndexCalculator().calculate_msi()
    out = TargetGenerator().generate_targets()
    return msi, out


def test_threshold_uses_only_past_msi(targets):
    msi, out = targets
    msi_values = msi["MSI"]

    for date in [out.index[0], out.index[len(out) // 2], out.index[-1]]:
        pos = msi_values.index.get_loc(date)
        past = msi_values.iloc[:pos].values  # strictly before t
        assert len(past) >= 252
        expected = np.quantile(past, STRESS_QUANTILE_THRESHOLD)
        assert out.loc[date, "Stress_Threshold"] == pytest.approx(expected)


def test_first_valid_date_requires_252_history(targets):
    msi, out = targets
    first_pos = msi.index.get_loc(out.index[0])
    assert first_pos == 252


def test_stress_event_is_msi_at_or_above_threshold(targets):
    _, out = targets
    expected = (out["MSI"] >= out["Stress_Threshold"]).astype(int)
    pd.testing.assert_series_equal(
        out["Is_Stress_Event"], expected, check_names=False
    )
    assert set(out["Is_Stress_Event"].unique()) == {0, 1}


@pytest.mark.parametrize("horizon", [1, 5, 10, 20])
def test_forward_target_is_any_event_in_next_h_days(targets, horizon):
    _, out = targets
    col = f"Target_{horizon}D"
    events = out["Is_Stress_Event"].values
    n = len(out)

    # Trailing rows with an incomplete forward window stay unknown.
    assert out[col].iloc[-horizon:].isna().all()
    assert out[col].iloc[:-horizon].notna().all()

    for i in range(0, n - horizon, 37):
        future = events[i + 1 : i + 1 + horizon]
        assert out[col].iloc[i] == int(future.max())


def test_targets_are_monotone_in_horizon(targets):
    _, out = targets
    valid = out.dropna(subset=["Target_20D"])
    assert (valid["Target_1D"] <= valid["Target_5D"]).all()
    assert (valid["Target_5D"] <= valid["Target_10D"]).all()
    assert (valid["Target_10D"] <= valid["Target_20D"]).all()


def test_target_dtypes_and_both_classes_present(targets):
    _, out = targets
    for h in [1, 5, 10, 20]:
        assert str(out[f"Target_{h}D"].dtype) == "Int64"
        valid = out[f"Target_{h}D"].dropna()
        assert valid.nunique() == 2
    assert out["Is_Stress_Event"].dtype.kind == "i"


def test_injected_stress_episode_becomes_events(targets, market_df):
    _, out = targets
    stress_window = market_df.index[STRESS_START:STRESS_START + STRESS_LEN]
    events_in_window = out.loc[out.index.intersection(stress_window), "Is_Stress_Event"]
    assert events_in_window.sum() > 0
