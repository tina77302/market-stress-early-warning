from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)

from src.models.logistic import build_logistic_model
from src.models.xgboost_model import build_xgboost_model


# ============================================================
# CONFIG
# ============================================================

FEATURE_MATRIX_PATH = Path("data/features/feature_matrix.csv")

OUTPUT_DIR = Path("data/processed/bitcoin_ablation")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET = "Target_10D"

MIN_TRAIN_SIZE = 5 * 252
STEP_SIZE = 21
PURGE = 10
THRESHOLD = 0.5


# ============================================================
# CORE 17 FEATURES
# ============================================================

CORE_FEATURES = [
    "SPY_1D_Return",
    "SPY_5D_Return",
    "SPY_20D_Return",
    "SPY_20D_Vol",
    "SPY_60D_Vol",
    "SPY_Drawdown",
    "SPY_20D_Momentum",

    "VIX_Level",
    "VIX_1D_Change",
    "VIX_5D_Change",
    "VIX_20D_Momentum",
    "VIX_252D_ZScore",

    "Credit_Level",
    "Credit_1D_Change",
    "Credit_5D_Change",
    "Credit_20D_Momentum",
    "Credit_252D_ZScore",
]


# ============================================================
# BTC EXTENSION FEATURES
# ============================================================

BTC_FEATURES = [
    "BTC_5D_Return",
    "BTC_20D_Return",
    "BTC_20D_Vol",
    "BTC_60D_Momentum",
]


# ============================================================
# LOAD CORE DATA
# ============================================================

def load_core_data():

    print("\n========== LOAD CORE FEATURE MATRIX ==========")

    df = pd.read_csv(
        FEATURE_MATRIX_PATH,
        index_col=0,
        parse_dates=True,
    )

    df.index = pd.to_datetime(df.index)

    required = CORE_FEATURES + [TARGET]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    print(f"Start : {df.index.min().date()}")
    print(f"End   : {df.index.max().date()}")
    print(f"Rows  : {len(df):,}")

    return df


# ============================================================
# DOWNLOAD + ALIGN BTC
# ============================================================

def build_btc_features(market_index):

    print("\n========== DOWNLOAD BTC ==========")

    btc = yf.download(
        "BTC-USD",
        start="2010-01-01",
        end="2026-10-07",
        auto_adjust=True,
        progress=False,
    )

    if btc.empty:
        raise RuntimeError(
            "BTC-USD download returned no data."
        )

    close = btc["Close"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close.index = pd.to_datetime(close.index)
    close = close.sort_index()
    close = close.rename("BTC_Close_Raw")

    print(
        f"Raw BTC: "
        f"{close.index.min().date()} → "
        f"{close.index.max().date()}"
    )

    print(f"Raw observations: {len(close):,}")

    # --------------------------------------------------------
    # Conservative timing alignment
    #
    # BTC trades 24/7. To avoid using information that may not
    # have been available at the U.S. equity-market decision
    # point on date t, use the previous completed BTC daily bar.
    # --------------------------------------------------------

    btc_lagged = close.shift(1)

    # Align BTC to U.S. market trading dates.
    #
    # Reindex over union first so weekend BTC observations are
    # retained for forward filling, then select market dates.
    combined_index = (
        btc_lagged.index
        .union(market_index)
        .sort_values()
    )

    aligned = (
        btc_lagged
        .reindex(combined_index)
        .ffill()
        .reindex(market_index)
    )

    aligned = aligned.rename("BTC_Close")

    btc_df = aligned.to_frame()

    # --------------------------------------------------------
    # IMPORTANT:
    # Features are calculated AFTER alignment to U.S. trading
    # dates, so 5D / 20D / 60D mean trading-day observations.
    # --------------------------------------------------------

    btc_return_1d = (
        btc_df["BTC_Close"]
        .pct_change(fill_method=None)
    )

    btc_df["BTC_5D_Return"] = (
        btc_df["BTC_Close"]
        .pct_change(
            5,
            fill_method=None,
        )
    )

    btc_df["BTC_20D_Return"] = (
        btc_df["BTC_Close"]
        .pct_change(
            20,
            fill_method=None,
        )
    )

    btc_df["BTC_20D_Vol"] = (
        btc_return_1d
        .rolling(20)
        .std()
        * np.sqrt(252)
    )

    btc_df["BTC_60D_Momentum"] = (
        btc_df["BTC_Close"]
        .pct_change(
            60,
            fill_method=None,
        )
    )

    print("\n========== BTC ALIGNED FEATURE QA ==========")

    for col in BTC_FEATURES:

        valid = btc_df[col].dropna()

        if valid.empty:
            raise RuntimeError(
                f"No valid observations for {col}"
            )

        print(
            f"{col}: "
            f"{valid.index.min().date()} → "
            f"{valid.index.max().date()} "
            f"| N={len(valid):,}"
        )

    return btc_df


# ============================================================
# PREPARE COMMON SAMPLE
# ============================================================

def prepare_common_sample(core_df, btc_df):

    print("\n========== PREPARE COMMON SAMPLE ==========")

    df = core_df.join(
        btc_df[BTC_FEATURES],
        how="left",
    )

    required = (
        CORE_FEATURES
        + BTC_FEATURES
        + [TARGET]
    )

    df = df.dropna(
        subset=required
    ).copy()

    df[TARGET] = (
        df[TARGET]
        .astype(int)
    )

    print(
        f"Common sample: "
        f"{df.index.min().date()} → "
        f"{df.index.max().date()}"
    )

    print(f"Observations : {len(df):,}")

    print(
        f"Target prevalence: "
        f"{df[TARGET].mean():.4%}"
    )

    if len(df) <= MIN_TRAIN_SIZE:
        raise RuntimeError(
            "Not enough common-sample observations "
            "for walk-forward validation."
        )

    return df


# ============================================================
# WALK-FORWARD
# ============================================================

def run_walk_forward(
    df,
    feature_cols,
    specification_name,
):

    print(
        f"\n========== WALK-FORWARD: "
        f"{specification_name} =========="
    )

    X = df[feature_cols]
    y = df[TARGET]

    result_parts = []

    fold = 0

    for test_start in range(
        MIN_TRAIN_SIZE,
        len(df),
        STEP_SIZE,
    ):

        test_end = min(
            test_start + STEP_SIZE,
            len(df),
        )

        # Target_10D uses information from t+1...t+10.
        # Purge the final 10 observations before test start
        # from the training sample.
        train_end = test_start - PURGE

        if train_end <= 0:
            continue

        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]

        X_test = X.iloc[
            test_start:test_end
        ]

        y_test = y.iloc[
            test_start:test_end
        ]

        if len(X_test) == 0:
            continue

        # Both classes are required.
        if y_train.nunique() < 2:
            continue

        positive = int(
            (y_train == 1).sum()
        )

        negative = int(
            (y_train == 0).sum()
        )

        if positive == 0:
            continue

        scale_pos_weight = (
            negative / positive
        )

        logistic = (
            build_logistic_model()
        )

        xgb = (
            build_xgboost_model(
                scale_pos_weight=scale_pos_weight
            )
        )

        logistic.fit(
            X_train,
            y_train,
        )

        xgb.fit(
            X_train,
            y_train,
        )

        logistic_prob = (
            logistic.predict_proba(
                X_test
            )[:, 1]
        )

        xgb_prob = (
            xgb.predict_proba(
                X_test
            )[:, 1]
        )

        fold_df = pd.DataFrame(
            {
                "Actual_Target":
                    y_test.values,

                "Logistic_Prob":
                    logistic_prob,

                "XGB_Prob":
                    xgb_prob,

                "Fold":
                    fold,
            },
            index=X_test.index,
        )

        result_parts.append(
            fold_df
        )

        fold += 1

    if not result_parts:
        raise RuntimeError(
            f"No OOS predictions generated for "
            f"{specification_name}"
        )

    results = pd.concat(
        result_parts
    ).sort_index()

    print(
        f"OOS period : "
        f"{results.index.min().date()} → "
        f"{results.index.max().date()}"
    )

    print(
        f"OOS observations : "
        f"{len(results):,}"
    )

    print(
        f"OOS prevalence : "
        f"{results['Actual_Target'].mean():.4%}"
    )

    return results


# ============================================================
# METRICS
# ============================================================

def calculate_model_metrics(
    results,
    probability_col,
    model_name,
    specification_name,
):

    y_true = (
        results["Actual_Target"]
        .astype(int)
    )

    y_prob = (
        results[probability_col]
        .astype(float)
    )

    y_pred = (
        y_prob >= THRESHOLD
    ).astype(int)

    tn, fp, fn, tp = (
        confusion_matrix(
            y_true,
            y_pred,
            labels=[0, 1],
        ).ravel()
    )

    far = (
        fp / (fp + tn)
        if (fp + tn) > 0
        else np.nan
    )

    missed = (
        fn / (fn + tp)
        if (fn + tp) > 0
        else np.nan
    )

    return {
        "Specification":
            specification_name,

        "Model":
            model_name,

        "Feature_Count":
            17
            if specification_name == "Core_17F"
            else 21,

        "OOS_Observations":
            len(results),

        "OOS_Prevalence":
            y_true.mean(),

        "ROC_AUC":
            roc_auc_score(
                y_true,
                y_prob,
            ),

        "PR_AUC":
            average_precision_score(
                y_true,
                y_prob,
            ),

        "Brier":
            brier_score_loss(
                y_true,
                y_prob,
            ),

        "Precision":
            precision_score(
                y_true,
                y_pred,
                zero_division=0,
            ),

        "Recall":
            recall_score(
                y_true,
                y_pred,
                zero_division=0,
            ),

        "F1":
            f1_score(
                y_true,
                y_pred,
                zero_division=0,
            ),

        "FAR":
            far,

        "Missed_Rate":
            missed,

        "TP":
            int(tp),

        "FP":
            int(fp),

        "TN":
            int(tn),

        "FN":
            int(fn),

        "OOS_Start":
            results.index.min(),

        "OOS_End":
            results.index.max(),
    }


# ============================================================
# DELTA TABLE
# ============================================================

def build_delta_table(metrics_df):

    metric_cols = [
        "ROC_AUC",
        "PR_AUC",
        "Brier",
        "Precision",
        "Recall",
        "F1",
        "FAR",
        "Missed_Rate",
    ]

    rows = []

    for model in [
        "Logistic",
        "XGBoost",
    ]:

        core = (
            metrics_df[
                (metrics_df["Model"] == model)
                &
                (
                    metrics_df["Specification"]
                    == "Core_17F"
                )
            ]
            .iloc[0]
        )

        btc = (
            metrics_df[
                (metrics_df["Model"] == model)
                &
                (
                    metrics_df["Specification"]
                    == "BTC_21F"
                )
            ]
            .iloc[0]
        )

        row = {
            "Model": model
        }

        for metric in metric_cols:
            row[
                f"Delta_{metric}"
            ] = (
                btc[metric]
                - core[metric]
            )

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        "============================================"
    )

    print(
        " BITCOIN EXTENSION ABLATION"
    )

    print(
        " Core 17F vs Core 17F + BTC 4F"
    )

    print(
        " Target: 10D Stress Event"
    )

    print(
        "============================================"
    )

    core_df = load_core_data()

    btc_df = build_btc_features(
        core_df.index
    )

    common_df = prepare_common_sample(
        core_df,
        btc_df,
    )

    # --------------------------------------------------------
    # SAME SAMPLE FOR BOTH SPECIFICATIONS
    # --------------------------------------------------------

    core_results = run_walk_forward(
        common_df,
        CORE_FEATURES,
        "Core_17F",
    )

    btc_results = run_walk_forward(
        common_df,
        CORE_FEATURES + BTC_FEATURES,
        "BTC_21F",
    )

    # Defensive check:
    # Both specifications MUST have identical OOS dates.
    if not core_results.index.equals(
        btc_results.index
    ):
        raise RuntimeError(
            "Core and BTC OOS indices do not match."
        )

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    metric_rows = []

    metric_rows.append(
        calculate_model_metrics(
            core_results,
            "Logistic_Prob",
            "Logistic",
            "Core_17F",
        )
    )

    metric_rows.append(
        calculate_model_metrics(
            core_results,
            "XGB_Prob",
            "XGBoost",
            "Core_17F",
        )
    )

    metric_rows.append(
        calculate_model_metrics(
            btc_results,
            "Logistic_Prob",
            "Logistic",
            "BTC_21F",
        )
    )

    metric_rows.append(
        calculate_model_metrics(
            btc_results,
            "XGB_Prob",
            "XGBoost",
            "BTC_21F",
        )
    )

    metrics_df = pd.DataFrame(
        metric_rows
    )

    delta_df = build_delta_table(
        metrics_df
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    core_results.to_csv(
        OUTPUT_DIR
        / "oos_core_17f.csv"
    )

    btc_results.to_csv(
        OUTPUT_DIR
        / "oos_btc_21f.csv"
    )

    metrics_df.to_csv(
        OUTPUT_DIR
        / "bitcoin_ablation_metrics.csv",
        index=False,
    )

    delta_df.to_csv(
        OUTPUT_DIR
        / "bitcoin_ablation_delta.csv",
        index=False,
    )

    # Save the aligned BTC extension features too.
    common_df[
        BTC_FEATURES
    ].to_csv(
        OUTPUT_DIR
        / "bitcoin_features_aligned.csv"
    )

    # --------------------------------------------------------
    # PRINT RESULTS
    # --------------------------------------------------------

    pd.set_option(
        "display.max_columns",
        None,
    )

    pd.set_option(
        "display.width",
        220,
    )

    print(
        "\n========== FINAL METRICS =========="
    )

    print(
        metrics_df.to_string(
            index=False
        )
    )

    print(
        "\n========== BTC - CORE DELTA =========="
    )

    print(
        delta_df.to_string(
            index=False
        )
    )

    print(
        "\n========== SAVED =========="
    )

    print(
        OUTPUT_DIR
        / "bitcoin_ablation_metrics.csv"
    )

    print(
        OUTPUT_DIR
        / "bitcoin_ablation_delta.csv"
    )

    print(
        "\nBITCOIN EXTENSION ABLATION COMPLETE"
    )


if __name__ == "__main__":
    main()