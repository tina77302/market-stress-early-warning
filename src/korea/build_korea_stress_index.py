import os

import numpy as np
import pandas as pd


# ============================================================
# Paths
# ============================================================

KRX_PATH = "data/raw/korea/krx_indices.csv"
VKOSPI_PATH = "data/raw/korea/vkospi.csv"
CREDIT_PATH = "data/raw/korea/ecos_credit.csv"

OUTPUT_PATH = "data/processed/korea/korea_stress_index.csv"


# ============================================================
# Methodology
# ============================================================

EQUITY_WINDOW = 21

# Past-only rolling normalization window
ZSCORE_WINDOW = 252

# Require enough observations before calculating rolling stats
ZSCORE_MIN_PERIODS = 126

# Past-only expanding stress threshold
STRESS_QUANTILE = 0.90

# Require at least one trading year before threshold estimation
THRESHOLD_MIN_PERIODS = 252


# ============================================================
# Past-only rolling z-score
# ============================================================

def past_only_rolling_zscore(
    series,
    window=ZSCORE_WINDOW,
    min_periods=ZSCORE_MIN_PERIODS,
):
    """
    Calculate a leakage-safe rolling z-score.

    For observation t:
    mean/std are estimated only from observations available
    strictly before t.

    Current observation t is NOT included in its own
    normalization parameters.
    """

    history = series.shift(1)

    rolling_mean = history.rolling(
        window=window,
        min_periods=min_periods,
    ).mean()

    rolling_std = history.rolling(
        window=window,
        min_periods=min_periods,
    ).std()

    rolling_std = rolling_std.replace(0, np.nan)

    zscore = (
        series - rolling_mean
    ) / rolling_std

    return zscore


# ============================================================
# Load KOSPI200
# ============================================================

def load_kospi200():

    if not os.path.exists(KRX_PATH):
        raise FileNotFoundError(
            f"KRX file not found: {KRX_PATH}"
        )

    df = pd.read_csv(KRX_PATH)

    df["Date"] = pd.to_datetime(df["Date"])

    df = df[
        df["Index"] == "KOSPI200"
    ].copy()

    if df.empty:
        raise ValueError(
            "KOSPI200 not found in KRX data."
        )

    df = df[
        [
            "Date",
            "Close",
        ]
    ].rename(
        columns={
            "Close": "KOSPI200"
        }
    )

    df = (
        df.sort_values("Date")
        .drop_duplicates(
            subset=["Date"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df


# ============================================================
# Load VKOSPI
# ============================================================

def load_vkospi():

    if not os.path.exists(VKOSPI_PATH):
        raise FileNotFoundError(
            f"VKOSPI file not found: {VKOSPI_PATH}"
        )

    df = pd.read_csv(VKOSPI_PATH)

    df["Date"] = pd.to_datetime(df["Date"])

    df = df[
        [
            "Date",
            "Close",
        ]
    ].rename(
        columns={
            "Close": "VKOSPI"
        }
    )

    df = (
        df.sort_values("Date")
        .drop_duplicates(
            subset=["Date"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df


# ============================================================
# Load Credit Spread
# ============================================================

def load_credit():

    if not os.path.exists(CREDIT_PATH):
        raise FileNotFoundError(
            f"Credit file not found: {CREDIT_PATH}"
        )

    df = pd.read_csv(CREDIT_PATH)

    df["Date"] = pd.to_datetime(df["Date"])

    required = [
        "Date",
        "Korea_Treasury_3Y",
        "Korea_Corporate_AAminus_3Y",
        "Korea_Credit_Spread",
        "Korea_Credit_Spread_bp",
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing credit columns: {missing}"
        )

    df = df[required].copy()

    df = (
        df.sort_values("Date")
        .drop_duplicates(
            subset=["Date"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df


# ============================================================
# Main
# ============================================================

def main():

    print("=" * 70)
    print("KOREA MARKET STRESS INDEX")
    print("=" * 70)

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    equity = load_kospi200()
    volatility = load_vkospi()
    credit = load_credit()

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    df = pd.merge(
        equity,
        volatility,
        on="Date",
        how="inner",
        validate="one_to_one",
    )

    df = pd.merge(
        df,
        credit,
        on="Date",
        how="inner",
        validate="one_to_one",
    )

    df = (
        df.sort_values("Date")
        .reset_index(drop=True)
    )

    print()
    print("Merged rows:", f"{len(df):,}")

    print(
        "Date range:",
        df["Date"].min().date(),
        "→",
        df["Date"].max().date(),
    )

    print()

    print("Raw missing values:")
    print(
        df[
            [
                "KOSPI200",
                "VKOSPI",
                "Korea_Credit_Spread",
            ]
        ].isna().sum()
    )

    # ========================================================
    # 1. EQUITY STRESS
    #
    # Negative 21-trading-day KOSPI200 return.
    #
    # A larger positive value means greater equity stress.
    # ========================================================

    df["KOSPI200_21D_Return"] = (
        df["KOSPI200"].pct_change(
            EQUITY_WINDOW
        )
    )

    df["Equity_Stress_Raw"] = (
        -df["KOSPI200_21D_Return"]
    )

    # ========================================================
    # 2. VOLATILITY STRESS
    #
    # VKOSPI level.
    #
    # Higher VKOSPI = greater volatility stress.
    # ========================================================

    df["Volatility_Stress_Raw"] = (
        df["VKOSPI"]
    )

    # ========================================================
    # 3. CREDIT STRESS
    #
    # AA- corporate 3Y yield
    # minus Korea Treasury 3Y yield.
    #
    # Higher spread = greater credit stress.
    # ========================================================

    df["Credit_Stress_Raw"] = (
        df["Korea_Credit_Spread"]
    )

    # ========================================================
    # Past-only normalization
    # ========================================================

    df["Equity_Stress_Z"] = (
        past_only_rolling_zscore(
            df["Equity_Stress_Raw"]
        )
    )

    df["Volatility_Stress_Z"] = (
        past_only_rolling_zscore(
            df["Volatility_Stress_Raw"]
        )
    )

    df["Credit_Stress_Z"] = (
        past_only_rolling_zscore(
            df["Credit_Stress_Raw"]
        )
    )

    # ========================================================
    # Korea MSI
    #
    # Equal-weight composite:
    #
    # 1/3 Equity
    # 1/3 Volatility
    # 1/3 Credit
    #
    # No weights are optimized against future Stress Events.
    # ========================================================

    z_columns = [
        "Equity_Stress_Z",
        "Volatility_Stress_Z",
        "Credit_Stress_Z",
    ]

    df["Korea_MSI"] = (
        df[z_columns]
        .mean(
            axis=1,
            skipna=False,
        )
    )

    # ========================================================
    # Past-only expanding threshold
    #
    # For date t, threshold is estimated using MSI observations
    # strictly before t.
    #
    # This avoids using future information when defining
    # historical Stress Events.
    # ========================================================

    msi_history = df["Korea_MSI"].shift(1)

    df["Stress_Threshold"] = (
        msi_history.expanding(
            min_periods=THRESHOLD_MIN_PERIODS
        )
        .quantile(
            STRESS_QUANTILE
        )
    )

    # ========================================================
    # Stress Event
    # ========================================================

    valid_event = (
        df["Korea_MSI"].notna()
        & df["Stress_Threshold"].notna()
    )

    df["Is_Stress_Event"] = pd.Series(
        pd.NA,
        index=df.index,
        dtype="Int64",
    )

    df.loc[
        valid_event,
        "Is_Stress_Event",
    ] = (
        df.loc[
            valid_event,
            "Korea_MSI",
        ]
        > df.loc[
            valid_event,
            "Stress_Threshold",
        ]
    ).astype(int)

    # ========================================================
    # QA
    # ========================================================

    print()
    print("=" * 70)
    print("MSI QA")
    print("=" * 70)

    print()
    print("Missing values:")

    print(
        df[
            [
                "KOSPI200_21D_Return",
                "Equity_Stress_Z",
                "Volatility_Stress_Z",
                "Credit_Stress_Z",
                "Korea_MSI",
                "Stress_Threshold",
                "Is_Stress_Event",
            ]
        ].isna().sum()
    )

    valid_msi = df[
        df["Korea_MSI"].notna()
    ].copy()

    valid_events = df[
        df["Is_Stress_Event"].notna()
    ].copy()

    print()
    print(
        "First valid MSI date:",
        valid_msi["Date"].min().date(),
    )

    print(
        "Valid MSI observations:",
        f"{len(valid_msi):,}",
    )

    print()

    print(
        "First valid Stress Event date:",
        valid_events["Date"].min().date(),
    )

    print(
        "Stress Event evaluation observations:",
        f"{len(valid_events):,}",
    )

    event_count = int(
        valid_events[
            "Is_Stress_Event"
        ].sum()
    )

    event_rate = (
        valid_events[
            "Is_Stress_Event"
        ].mean()
    )

    print(
        "Stress Event days:",
        f"{event_count:,}",
    )

    print(
        "Stress Event rate:",
        f"{event_rate:.4%}",
    )

    # ========================================================
    # Largest MSI observations
    # ========================================================

    print()
    print("=" * 70)
    print("TOP 30 KOREA MSI DAYS")
    print("=" * 70)

    top_days = (
        valid_events[
            [
                "Date",
                "KOSPI200",
                "VKOSPI",
                "Korea_Credit_Spread_bp",
                "Equity_Stress_Z",
                "Volatility_Stress_Z",
                "Credit_Stress_Z",
                "Korea_MSI",
                "Stress_Threshold",
                "Is_Stress_Event",
            ]
        ]
        .nlargest(
            30,
            "Korea_MSI",
        )
    )

    print(
        top_days.to_string(
            index=False
        )
    )

    # ========================================================
    # Stress events by year
    # ========================================================

    print()
    print("=" * 70)
    print("STRESS EVENT DAYS BY YEAR")
    print("=" * 70)

    event_by_year = (
        valid_events
        .assign(
            Year=valid_events[
                "Date"
            ].dt.year
        )
        .groupby("Year")[
            "Is_Stress_Event"
        ]
        .agg(
            [
                "count",
                "sum",
                "mean",
            ]
        )
    )

    event_by_year = event_by_year.rename(
        columns={
            "count": "Evaluated_Days",
            "sum": "Stress_Days",
            "mean": "Stress_Rate",
        }
    )

    print(event_by_year)

    # ========================================================
    # Summary statistics
    # ========================================================

    print()
    print("=" * 70)
    print("MSI SUMMARY")
    print("=" * 70)

    print(
        valid_msi[
            [
                "Equity_Stress_Z",
                "Volatility_Stress_Z",
                "Credit_Stress_Z",
                "Korea_MSI",
            ]
        ]
        .describe()
        .T
    )

    # ========================================================
    # Save
    # ========================================================

    os.makedirs(
        os.path.dirname(OUTPUT_PATH),
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("=" * 70)
    print("SAVE COMPLETE")
    print("=" * 70)

    print("Saved:", OUTPUT_PATH)
    print("Rows:", f"{len(df):,}")

    print()
    print(
        "Methodology:"
    )

    print(
        "- Equity: negative KOSPI200 21D return"
    )

    print(
        "- Volatility: VKOSPI level"
    )

    print(
        "- Credit: AA- 3Y corporate minus Treasury 3Y"
    )

    print(
        "- Normalization: past-only 252D rolling z-score"
    )

    print(
        "- Composite: equal-weight mean of 3 stress channels"
    )

    print(
        "- Event threshold: past-only expanding 90th percentile"
    )

    print(
        "- No future observations are used in normalization "
        "or threshold estimation"
    )


if __name__ == "__main__":
    main()