import os
import pandas as pd
import numpy as np


# ============================================================
# Paths
# ============================================================

KRX_PATH = "data/raw/korea/krx_indices.csv"
VKOSPI_PATH = "data/raw/korea/vkospi.csv"


# ============================================================
# Load KRX indices
# ============================================================

def load_krx_indices():

    if not os.path.exists(KRX_PATH):
        raise FileNotFoundError(
            f"KRX file not found: {KRX_PATH}"
        )

    df = pd.read_csv(KRX_PATH)

    df["Date"] = pd.to_datetime(df["Date"])

    print("=" * 60)
    print("KRX INDEX DATA")
    print("=" * 60)

    print("Rows:", f"{len(df):,}")
    print()

    print("Columns:")
    print(df.columns.tolist())
    print()

    print("Index names:")
    print(df["Index"].value_counts())
    print()

    # --------------------------------------------------------
    # Pivot close prices
    # --------------------------------------------------------

    close = df.pivot(
        index="Date",
        columns="Index",
        values="Close",
    ).reset_index()

    required = [
        "KOSPI",
        "KOSPI200",
    ]

    for col in required:
        if col not in close.columns:
            raise ValueError(
                f"{col} not found in KRX data."
            )

    close = close[
        [
            "Date",
            "KOSPI",
            "KOSPI200",
        ]
    ].copy()

    return close


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

    if "Close" not in df.columns:
        raise ValueError(
            "Close column not found in VKOSPI data."
        )

    df = df[
        [
            "Date",
            "Close",
        ]
    ].copy()

    df = df.rename(
        columns={
            "Close": "VKOSPI"
        }
    )

    return df


# ============================================================
# Drawdown
# ============================================================

def calculate_drawdown(series):

    running_max = series.cummax()

    return (
        series / running_max
        - 1
    )


# ============================================================
# Main
# ============================================================

def main():

    kospi = load_krx_indices()
    vkospi = load_vkospi()

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    df = pd.merge(
        kospi,
        vkospi,
        on="Date",
        how="inner",
        validate="one_to_one",
    )

    df = (
        df.sort_values("Date")
        .reset_index(drop=True)
    )

    print("=" * 60)
    print("MERGED DATA")
    print("=" * 60)

    print("Rows:", f"{len(df):,}")

    print(
        "Date range:",
        df["Date"].min().date(),
        "→",
        df["Date"].max().date(),
    )

    print()

    print("Missing values:")
    print(df.isna().sum())

    print()

    # ========================================================
    # Returns
    # ========================================================

    df["KOSPI_1D_Return"] = (
        df["KOSPI"].pct_change()
    )

    df["KOSPI200_1D_Return"] = (
        df["KOSPI200"].pct_change()
    )

    df["KOSPI_5D_Return"] = (
        df["KOSPI"].pct_change(5)
    )

    df["KOSPI200_5D_Return"] = (
        df["KOSPI200"].pct_change(5)
    )

    df["KOSPI_20D_Return"] = (
        df["KOSPI"].pct_change(20)
    )

    df["KOSPI200_20D_Return"] = (
        df["KOSPI200"].pct_change(20)
    )

    # ========================================================
    # Realized volatility
    # ========================================================

    df["KOSPI_20D_Vol"] = (
        df["KOSPI_1D_Return"]
        .rolling(20)
        .std()
        * np.sqrt(252)
    )

    df["KOSPI200_20D_Vol"] = (
        df["KOSPI200_1D_Return"]
        .rolling(20)
        .std()
        * np.sqrt(252)
    )

    # ========================================================
    # Drawdown
    # ========================================================

    df["KOSPI_Drawdown"] = (
        calculate_drawdown(
            df["KOSPI"]
        )
    )

    df["KOSPI200_Drawdown"] = (
        calculate_drawdown(
            df["KOSPI200"]
        )
    )

    # ========================================================
    # Correlation analysis
    # ========================================================

    print("=" * 60)
    print("KOSPI vs KOSPI200")
    print("=" * 60)

    level_corr = (
        df["KOSPI"]
        .corr(df["KOSPI200"])
    )

    return_1d_corr = (
        df["KOSPI_1D_Return"]
        .corr(
            df["KOSPI200_1D_Return"]
        )
    )

    return_5d_corr = (
        df["KOSPI_5D_Return"]
        .corr(
            df["KOSPI200_5D_Return"]
        )
    )

    return_20d_corr = (
        df["KOSPI_20D_Return"]
        .corr(
            df["KOSPI200_20D_Return"]
        )
    )

    vol_corr = (
        df["KOSPI_20D_Vol"]
        .corr(
            df["KOSPI200_20D_Vol"]
        )
    )

    drawdown_corr = (
        df["KOSPI_Drawdown"]
        .corr(
            df["KOSPI200_Drawdown"]
        )
    )

    print(
        f"Price level correlation: "
        f"{level_corr:.6f}"
    )

    print(
        f"1D return correlation: "
        f"{return_1d_corr:.6f}"
    )

    print(
        f"5D return correlation: "
        f"{return_5d_corr:.6f}"
    )

    print(
        f"20D return correlation: "
        f"{return_20d_corr:.6f}"
    )

    print(
        f"20D volatility correlation: "
        f"{vol_corr:.6f}"
    )

    print(
        f"Drawdown correlation: "
        f"{drawdown_corr:.6f}"
    )

    print()

    # ========================================================
    # VKOSPI relationship
    #
    # VKOSPI is expected to move opposite equity returns
    # and positively with realized volatility.
    # ========================================================

    print("=" * 60)
    print("RELATIONSHIP WITH VKOSPI")
    print("=" * 60)

    kospi_return_vkospi = (
        df["KOSPI_1D_Return"]
        .corr(df["VKOSPI"])
    )

    kospi200_return_vkospi = (
        df["KOSPI200_1D_Return"]
        .corr(df["VKOSPI"])
    )

    kospi_vol_vkospi = (
        df["KOSPI_20D_Vol"]
        .corr(df["VKOSPI"])
    )

    kospi200_vol_vkospi = (
        df["KOSPI200_20D_Vol"]
        .corr(df["VKOSPI"])
    )

    print(
        "KOSPI 1D return vs VKOSPI:",
        f"{kospi_return_vkospi:.6f}",
    )

    print(
        "KOSPI200 1D return vs VKOSPI:",
        f"{kospi200_return_vkospi:.6f}",
    )

    print(
        "KOSPI 20D vol vs VKOSPI:",
        f"{kospi_vol_vkospi:.6f}",
    )

    print(
        "KOSPI200 20D vol vs VKOSPI:",
        f"{kospi200_vol_vkospi:.6f}",
    )

    print()

    # ========================================================
    # Large negative-return days
    #
    # This is descriptive QA only.
    # No threshold here will be used as the final Stress Event.
    # ========================================================

    print("=" * 60)
    print("LARGEST 1D EQUITY DECLINES")
    print("=" * 60)

    print()
    print("KOSPI — 15 largest declines")

    print(
        df[
            [
                "Date",
                "KOSPI_1D_Return",
                "KOSPI200_1D_Return",
                "VKOSPI",
            ]
        ]
        .nsmallest(
            15,
            "KOSPI_1D_Return",
        )
        .to_string(index=False)
    )

    print()

    print("KOSPI200 — 15 largest declines")

    print(
        df[
            [
                "Date",
                "KOSPI_1D_Return",
                "KOSPI200_1D_Return",
                "VKOSPI",
            ]
        ]
        .nsmallest(
            15,
            "KOSPI200_1D_Return",
        )
        .to_string(index=False)
    )

    print()

    # ========================================================
    # Largest 20D declines
    # ========================================================

    print("=" * 60)
    print("LARGEST 20D EQUITY DECLINES")
    print("=" * 60)

    print()
    print("KOSPI — 15 largest 20D declines")

    print(
        df[
            [
                "Date",
                "KOSPI_20D_Return",
                "KOSPI200_20D_Return",
                "VKOSPI",
            ]
        ]
        .nsmallest(
            15,
            "KOSPI_20D_Return",
        )
        .to_string(index=False)
    )

    print()

    print(
        "KOSPI200 — 15 largest 20D declines"
    )

    print(
        df[
            [
                "Date",
                "KOSPI_20D_Return",
                "KOSPI200_20D_Return",
                "VKOSPI",
            ]
        ]
        .nsmallest(
            15,
            "KOSPI200_20D_Return",
        )
        .to_string(index=False)
    )

    print()

    # ========================================================
    # Difference between the two indices
    # ========================================================

    df["Return_Difference_1D"] = (
        df["KOSPI200_1D_Return"]
        - df["KOSPI_1D_Return"]
    )

    df["Return_Difference_20D"] = (
        df["KOSPI200_20D_Return"]
        - df["KOSPI_20D_Return"]
    )

    print("=" * 60)
    print("RETURN DIFFERENCE")
    print("=" * 60)

    print(
        "Mean absolute 1D return difference:",
        f"{df['Return_Difference_1D'].abs().mean():.6f}",
    )

    print(
        "Mean absolute 20D return difference:",
        f"{df['Return_Difference_20D'].abs().mean():.6f}",
    )

    print()

    # ========================================================
    # Summary statistics
    # ========================================================

    print("=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)

    summary_columns = [
        "KOSPI_1D_Return",
        "KOSPI200_1D_Return",
        "KOSPI_20D_Return",
        "KOSPI200_20D_Return",
        "KOSPI_20D_Vol",
        "KOSPI200_20D_Vol",
        "KOSPI_Drawdown",
        "KOSPI200_Drawdown",
        "VKOSPI",
    ]

    print(
        df[summary_columns]
        .describe()
        .T
    )

    print()

    print("=" * 60)
    print("QA COMPLETE")
    print("=" * 60)

    print(
        "This analysis is descriptive only. "
        "No model-performance metric was used "
        "to select the Korean equity index."
    )


if __name__ == "__main__":
    main()