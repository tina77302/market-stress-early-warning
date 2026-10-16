import numpy as np
import pandas as pd
import pytest

from src.data.cleaner import MarketDataCleaner


def _write_raw(data_dirs, df):
    path = data_dirs.DATA_RAW_DIR / "raw_market_data.csv"
    df.to_csv(path)
    return path


def _raw_frame(n=12):
    dates = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame(
        {
            "SPY": np.linspace(100, 111, n),
            "VIX": np.linspace(15, 26, n),
            "BAA_Treasury_Spread": np.linspace(2.0, 3.1, n),
        },
        index=pd.Index(dates, name="Date"),
    )


def test_missing_input_raises(data_dirs):
    with pytest.raises(FileNotFoundError):
        MarketDataCleaner().clean()


def test_spy_calendar_is_master(data_dirs):
    df = _raw_frame()
    # Bond-market-only dates (no SPY print) must be dropped, never filled.
    df.loc[df.index[3], "SPY"] = np.nan
    df.loc[df.index[7], "SPY"] = np.nan
    _write_raw(data_dirs, df)

    out = MarketDataCleaner().clean()

    assert len(out) == len(df) - 2
    assert df.index[3] not in out.index
    assert df.index[7] not in out.index
    assert out["SPY"].notna().all()


def test_short_gaps_forward_filled_long_gaps_dropped(data_dirs):
    df = _raw_frame(n=20)
    # 3-day VIX gap -> fully forward-filled.
    df.loc[df.index[2:5], "VIX"] = np.nan
    # 7-day credit gap -> first 5 filled, last 2 unresolved and dropped.
    df.loc[df.index[8:15], "BAA_Treasury_Spread"] = np.nan
    _write_raw(data_dirs, df)

    out = MarketDataCleaner().clean()

    # VIX gap filled with last observed value (row 1).
    for i in range(2, 5):
        assert out.loc[df.index[i], "VIX"] == pytest.approx(df.loc[df.index[1], "VIX"])

    # Credit: rows 8..12 filled with row 7's value, rows 13 and 14 dropped.
    for i in range(8, 13):
        assert out.loc[df.index[i], "BAA_Treasury_Spread"] == pytest.approx(
            df.loc[df.index[7], "BAA_Treasury_Spread"]
        )
    assert df.index[13] not in out.index
    assert df.index[14] not in out.index
    assert out.isna().sum().sum() == 0


def test_duplicate_dates_removed_keep_first(data_dirs):
    df = _raw_frame()
    dup = df.iloc[[4]].copy()
    dup["SPY"] = 999.0
    df = pd.concat([df, dup]).sort_index()
    _write_raw(data_dirs, df)

    out = MarketDataCleaner().clean()

    assert not out.index.duplicated().any()
    assert out.loc[df.index[4], "SPY"] != 999.0


@pytest.mark.parametrize("column", ["SPY", "VIX"])
def test_non_positive_prices_raise(data_dirs, column):
    df = _raw_frame()
    df.loc[df.index[5], column] = 0.0
    _write_raw(data_dirs, df)

    with pytest.raises(ValueError, match=column):
        MarketDataCleaner().clean()


def test_output_written_sorted(data_dirs):
    df = _raw_frame()
    _write_raw(data_dirs, df.iloc[::-1])  # reversed on disk

    out = MarketDataCleaner().clean()
    saved = pd.read_csv(
        data_dirs.DATA_PROCESSED_DIR / "cleaned_market_data.csv",
        index_col="Date",
        parse_dates=True,
    )

    assert out.index.is_monotonic_increasing
    assert list(saved.columns) == ["SPY", "VIX", "BAA_Treasury_Spread"]
    pd.testing.assert_frame_equal(saved, out, check_freq=False)
