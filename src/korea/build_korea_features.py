import os
import numpy as np
import pandas as pd


# ============================================================
# Paths
# ============================================================

KRX_PATH = "data/raw/korea/krx_indices.csv"
VKOSPI_PATH = "data/raw/korea/vkospi.csv"
CREDIT_PATH = "data/raw/korea/ecos_credit.csv"
TARGET_PATH = "data/processed/korea/korea_targets.csv"

OUTPUT_PATH = "data/processed/korea/korea_feature_matrix.csv"
LATEST_OUTPUT_PATH = "data/processed/korea/korea_latest_features.csv"


# ============================================================
# Final Korea 17-feature specification
# ============================================================

FEATURE_COLS = [
    # KOSPI200
    "KOSPI200_1D_Return",
    "KOSPI200_5D_Return",
    "KOSPI200_20D_Return",
    "KOSPI200_20D_Vol",
    "KOSPI200_60D_Vol",
    "KOSPI200_Drawdown",
    "KOSPI200_20D_Momentum",

    # VKOSPI
    "VKOSPI_Level",
    "VKOSPI_1D_Change",
    "VKOSPI_5D_Change",
    "VKOSPI_20D_Momentum",
    "VKOSPI_252D_ZScore",

    # Credit
    "Credit_Level",
    "Credit_1D_Change",
    "Credit_5D_Change",
    "Credit_20D_Momentum",
    "Credit_252D_ZScore",
]


def load_data():

    # --------------------------------------------------------
    # KRX indices
    # --------------------------------------------------------

    krx = pd.read_csv(KRX_PATH)
    krx["Date"] = pd.to_datetime(krx["Date"])

    # krx_indices.csv is long format:
    # Date / Index / Close / ...
    #
    # Convert KOSPI200 close into one daily column.
    kospi200 = (
        krx.loc[
            krx["Index"] == "KOSPI200",
            ["Date", "Close"],
        ]
        .rename(
            columns={
                "Close": "KOSPI200"
            }
        )
        .copy()
    )

    # --------------------------------------------------------
    # VKOSPI
    # --------------------------------------------------------

    vkospi = pd.read_csv(VKOSPI_PATH)
    vkospi["Date"] = pd.to_datetime(vkospi["Date"])

    # Find close column defensively.
    if "VKOSPI" in vkospi.columns:
        vkospi_daily = vkospi[
            ["Date", "VKOSPI"]
        ].copy()

    elif "Close" in vkospi.columns:
        vkospi_daily = (
            vkospi[
                ["Date", "Close"]
            ]
            .rename(
                columns={
                    "Close": "VKOSPI"
                }
            )
            .copy()
        )

    else:
        raise ValueError(
            "Could not find VKOSPI value column. "
            f"Available columns: {vkospi.columns.tolist()}"
        )

    # --------------------------------------------------------
    # Korea credit spread
    # --------------------------------------------------------

    credit = pd.read_csv(CREDIT_PATH)
    credit["Date"] = pd.to_datetime(credit["Date"])

    if "Korea_Credit_Spread" not in credit.columns:
        raise ValueError(
            "Korea_Credit_Spread column not found. "
            f"Available columns: {credit.columns.tolist()}"
        )

    credit_daily = credit[
        [
            "Date",
            "Korea_Credit_Spread",
        ]
    ].copy()

    # --------------------------------------------------------
    # Merge raw market channels
    # --------------------------------------------------------

    df = (
        kospi200
        .merge(
            vkospi_daily,
            on="Date",
            how="inner",
        )
        .merge(
            credit_daily,
            on="Date",
            how="inner",
        )
        .sort_values("Date")
        .reset_index(drop=True)
    )

    return df


def build_features(df):

    # ========================================================
    # 1. KOSPI200 FEATURES
    #
    # U.S. analogue: SPY
    # ========================================================

    df["KOSPI200_1D_Return"] = (
        df["KOSPI200"].pct_change(1)
    )

    df["KOSPI200_5D_Return"] = (
        df["KOSPI200"].pct_change(5)
    )

    df["KOSPI200_20D_Return"] = (
        df["KOSPI200"].pct_change(20)
    )

    df["KOSPI200_20D_Vol"] = (
        df["KOSPI200_1D_Return"]
        .rolling(20)
        .std()
        * np.sqrt(252)
    )

    df["KOSPI200_60D_Vol"] = (
        df["KOSPI200_1D_Return"]
        .rolling(60)
        .std()
        * np.sqrt(252)
    )

    historical_peak = (
        df["KOSPI200"].cummax()
    )

    df["KOSPI200_Drawdown"] = (
        (
            df["KOSPI200"]
            - historical_peak
        )
        / historical_peak
    )

    df["KOSPI200_20D_Momentum"] = (
        df["KOSPI200"]
        / df["KOSPI200"]
        .rolling(20)
        .mean()
        - 1.0
    )

    # ========================================================
    # 2. VKOSPI FEATURES
    #
    # U.S. analogue: VIX
    # ========================================================

    df["VKOSPI_Level"] = (
        df["VKOSPI"]
    )

    df["VKOSPI_1D_Change"] = (
        df["VKOSPI"].diff(1)
    )

    df["VKOSPI_5D_Change"] = (
        df["VKOSPI"].diff(5)
    )

    df["VKOSPI_20D_Momentum"] = (
        df["VKOSPI"]
        / df["VKOSPI"]
        .rolling(20)
        .mean()
        - 1.0
    )

    # Current t value compared with distribution
    # available through t-1.
    vkospi_history = (
        df["VKOSPI"].shift(1)
    )

    vkospi_mean = (
        vkospi_history
        .rolling(
            252,
            min_periods=60,
        )
        .mean()
    )

    vkospi_std = (
        vkospi_history
        .rolling(
            252,
            min_periods=60,
        )
        .std()
    )

    df["VKOSPI_252D_ZScore"] = (
        (
            df["VKOSPI"]
            - vkospi_mean
        )
        / (
            vkospi_std
            + 1e-8
        )
    )

    # ========================================================
    # 3. CREDIT FEATURES
    #
    # U.S. analogue:
    # BAA corporate yield - Treasury yield
    #
    # Korea:
    # AA- 3Y corporate bond yield
    # minus Korea Treasury 3Y yield
    # ========================================================

    df["Credit_Level"] = (
        df["Korea_Credit_Spread"]
    )

    df["Credit_1D_Change"] = (
        df["Korea_Credit_Spread"]
        .diff(1)
    )

    df["Credit_5D_Change"] = (
        df["Korea_Credit_Spread"]
        .diff(5)
    )

    df["Credit_20D_Momentum"] = (
        df["Korea_Credit_Spread"]
        / df["Korea_Credit_Spread"]
        .rolling(20)
        .mean()
        - 1.0
    )

    credit_history = (
        df["Korea_Credit_Spread"]
        .shift(1)
    )

    credit_mean = (
        credit_history
        .rolling(
            252,
            min_periods=60,
        )
        .mean()
    )

    credit_std = (
        credit_history
        .rolling(
            252,
            min_periods=60,
        )
        .std()
    )

    df["Credit_252D_ZScore"] = (
        (
            df["Korea_Credit_Spread"]
            - credit_mean
        )
        / (
            credit_std
            + 1e-8
        )
    )

    return df


def main(*, inference_only=False):

    print("=" * 72)
    print("KOREA MARKET FEATURE ENGINEERING")
    print("=" * 72)

    # --------------------------------------------------------
    # 1. Load
    # --------------------------------------------------------

    df = load_data()

    print()
    print(
        "Merged raw observations:",
        f"{len(df):,}",
    )

    print(
        "Raw date range:",
        df["Date"].min().date(),
        "→",
        df["Date"].max().date(),
    )

    # --------------------------------------------------------
    # 2. Basic raw-data QA
    # --------------------------------------------------------

    if df["Date"].duplicated().any():
        raise ValueError(
            "Duplicate dates found in merged Korea data."
        )

    raw_cols = [
        "KOSPI200",
        "VKOSPI",
        "Korea_Credit_Spread",
    ]

    if df[raw_cols].isna().any().any():
        raise ValueError(
            "Missing values found in Korea raw market channels."
        )

    # --------------------------------------------------------
    # 3. Generate features
    # --------------------------------------------------------

    df = build_features(df)

    before = len(df)

    feature_df = (
        df.dropna(
            subset=FEATURE_COLS
        )
        .copy()
    )

    dropped = (
        before
        - len(feature_df)
    )

    print()
    print(
        "Feature warm-up rows dropped:",
        f"{dropped:,}",
    )

    print(
        "Feature-ready observations:",
        f"{len(feature_df):,}",
    )

    print(
        "Feature-ready range:",
        feature_df["Date"].min().date(),
        "→",
        feature_df["Date"].max().date(),
    )

    # --------------------------------------------------------
    # 4. Save latest/inference feature history
    #
    # This does NOT require future Target_10D labels.
    # --------------------------------------------------------

    os.makedirs(
        os.path.dirname(
            LATEST_OUTPUT_PATH
        ),
        exist_ok=True,
    )

    latest_cols = [
        "Date",
        "KOSPI200",
        "VKOSPI",
        "Korea_Credit_Spread",
    ] + FEATURE_COLS

    feature_df[
        latest_cols
    ].to_csv(
        LATEST_OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    # Operational inference needs only observable features, not cached research
    # labels. The worker still validates all features, MSI and frozen inference.
    # Default research execution retains its target join and all existing QA.
    if inference_only:
        return

    # --------------------------------------------------------
    # 5. Load targets
    # --------------------------------------------------------

    targets = pd.read_csv(
        TARGET_PATH
    )

    targets["Date"] = pd.to_datetime(
        targets["Date"]
    )

    target_cols = [
        "Korea_MSI",
        "Stress_Threshold",
        "Is_Stress_Event",
        "Target_1D",
        "Target_5D",
        "Target_10D",
        "Target_20D",
    ]

    missing_targets = [
        col
        for col in target_cols
        if col not in targets.columns
    ]

    if missing_targets:
        raise ValueError(
            "Missing target columns: "
            f"{missing_targets}"
        )

    targets = targets[
        ["Date"] + target_cols
    ].copy()

    # --------------------------------------------------------
    # 6. Join X and y by trading date
    # --------------------------------------------------------

    final_df = (
        feature_df
        .merge(
            targets,
            on="Date",
            how="inner",
        )
        .sort_values("Date")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # 7. Final QA
    # --------------------------------------------------------

    if final_df["Date"].duplicated().any():
        raise ValueError(
            "Duplicate dates found in Korea feature matrix."
        )

    if (
        final_df[
            FEATURE_COLS
        ]
        .isna()
        .any()
        .any()
    ):
        raise ValueError(
            "Missing values remain in Korea ML features."
        )

    print()
    print("=" * 72)
    print("FINAL FEATURE MATRIX QA")
    print("=" * 72)

    print()
    print(
        "Final rows:",
        f"{len(final_df):,}",
    )

    print(
        "Final range:",
        final_df["Date"].min().date(),
        "→",
        final_df["Date"].max().date(),
    )

    print(
        "Number of ML features:",
        len(FEATURE_COLS),
    )

    valid_10d = (
        final_df["Target_10D"]
        .dropna()
    )

    print(
        "Valid Target_10D observations:",
        f"{len(valid_10d):,}",
    )

    print(
        "Target_10D positives:",
        f"{int(valid_10d.sum()):,}",
    )

    print(
        "Target_10D prevalence:",
        f"{valid_10d.mean():.4%}",
    )

    print(
        "Target_10D end NaN:",
        f"{final_df['Target_10D'].isna().sum():,}",
    )

    print()

    print(
        "Feature missing values:",
        int(
            final_df[
                FEATURE_COLS
            ]
            .isna()
            .sum()
            .sum()
        ),
    )

    # --------------------------------------------------------
    # 8. Feature list
    # --------------------------------------------------------

    print()
    print("-" * 72)
    print("FINAL KOREA 17 FEATURES")
    print("-" * 72)

    for i, feature in enumerate(
        FEATURE_COLS,
        start=1,
    ):
        print(
            f"{i:02d}. {feature}"
        )

    # --------------------------------------------------------
    # 9. Latest observation
    # --------------------------------------------------------

    latest = (
        feature_df
        .iloc[-1]
    )

    print()
    print("-" * 72)
    print("LATEST MARKET OBSERVATION")
    print("-" * 72)

    print(
        "Date:",
        latest["Date"].date(),
    )

    print(
        "KOSPI200:",
        f"{latest['KOSPI200']:.4f}",
    )

    print(
        "VKOSPI:",
        f"{latest['VKOSPI']:.4f}",
    )

    print(
        "Korea Credit Spread:",
        f"{latest['Korea_Credit_Spread']:.4f}",
    )

    # --------------------------------------------------------
    # 10. Save final matrix
    # --------------------------------------------------------

    final_output_cols = (
        [
            "Date",
            "KOSPI200",
            "VKOSPI",
            "Korea_Credit_Spread",
        ]
        + FEATURE_COLS
        + target_cols
    )

    final_df[
        final_output_cols
    ].to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("=" * 72)
    print("SAVE COMPLETE")
    print("=" * 72)

    print(
        "Feature matrix:",
        OUTPUT_PATH,
    )

    print(
        "Inference features:",
        LATEST_OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()