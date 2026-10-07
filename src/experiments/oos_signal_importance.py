from pathlib import Path
import time

import numpy as np
import pandas as pd

from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
)

from src.models.logistic import build_logistic_model
from src.models.xgboost_model import build_xgboost_model


# ============================================================
# CONFIG
# ============================================================

FEATURE_PATH = Path("data/features/feature_matrix.csv")

OUTPUT_DIR = Path(
    "data/processed/oos_signal_importance"
)
OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

TARGET = "Target_10D"

MIN_TRAIN_SIZE = 5 * 252
STEP = 21
PURGE = 10


FEATURES = [
    # SPY
    "SPY_1D_Return",
    "SPY_5D_Return",
    "SPY_20D_Return",
    "SPY_20D_Vol",
    "SPY_60D_Vol",
    "SPY_Drawdown",
    "SPY_20D_Momentum",

    # VIX
    "VIX_Level",
    "VIX_1D_Change",
    "VIX_5D_Change",
    "VIX_20D_Momentum",
    "VIX_252D_ZScore",

    # Credit
    "Credit_Level",
    "Credit_1D_Change",
    "Credit_5D_Change",
    "Credit_20D_Momentum",
    "Credit_252D_ZScore",
]


# ============================================================
# LOAD DATA
# ============================================================

def load_data():

    print(
        "\n========== LOAD DATA =========="
    )

    df = pd.read_csv(
        FEATURE_PATH,
        index_col=0,
        parse_dates=True,
    )

    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    required = FEATURES + [TARGET]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing columns: {missing}"
        )

    # Drop rows where target is unavailable.
    df = df.dropna(
        subset=[TARGET]
    ).copy()

    # Feature QA
    feature_nan = (
        df[FEATURES]
        .isna()
        .sum()
    )

    bad_features = feature_nan[
        feature_nan > 0
    ]

    if len(bad_features) > 0:
        raise ValueError(
            "Feature NaNs detected:\n"
            f"{bad_features}"
        )

    df[TARGET] = (
        df[TARGET]
        .astype(int)
    )

    print(
        f"Period: "
        f"{df.index.min().date()} "
        f"→ {df.index.max().date()}"
    )

    print(
        f"Samples: {len(df):,}"
    )

    print(
        f"Target prevalence: "
        f"{df[TARGET].mean():.4%}"
    )

    print(
        f"Features: {len(FEATURES)}"
    )

    return df


# ============================================================
# WALK-FORWARD OOS
# ============================================================

def run_walk_forward(
    df,
    feature_cols,
):

    X = df[feature_cols]
    y = df[TARGET]

    logistic_prob = np.full(
        len(df),
        np.nan,
        dtype=float,
    )

    xgb_prob = np.full(
        len(df),
        np.nan,
        dtype=float,
    )

    fold = 0

    for test_start in range(
        MIN_TRAIN_SIZE,
        len(df),
        STEP,
    ):

        test_end = min(
            test_start + STEP,
            len(df),
        )

        # --------------------------------------------
        # 10D label-overlap purge
        #
        # Train rows end BEFORE test_start - 10.
        # iloc end is exclusive.
        # --------------------------------------------

        train_end = (
            test_start - PURGE
        )

        if train_end <= 0:
            continue

        X_train = X.iloc[
            :train_end
        ]

        y_train = y.iloc[
            :train_end
        ]

        X_test = X.iloc[
            test_start:test_end
        ]

        if len(X_test) == 0:
            continue

        # Need both classes in training sample.
        if y_train.nunique() < 2:
            continue

        negative = int(
            (y_train == 0).sum()
        )

        positive = int(
            (y_train == 1).sum()
        )

        if positive == 0:
            continue

        scale_pos_weight = (
            negative / positive
        )

        # --------------------------------------------
        # Logistic
        # --------------------------------------------

        logistic = (
            build_logistic_model()
        )

        logistic.fit(
            X_train,
            y_train,
        )

        logistic_prob[
            test_start:test_end
        ] = logistic.predict_proba(
            X_test
        )[:, 1]

        # --------------------------------------------
        # XGBoost
        # --------------------------------------------

        xgb = build_xgboost_model(
            scale_pos_weight=scale_pos_weight
        )

        xgb.fit(
            X_train,
            y_train,
        )

        xgb_prob[
            test_start:test_end
        ] = xgb.predict_proba(
            X_test
        )[:, 1]

        fold += 1

    valid = (
        ~np.isnan(logistic_prob)
        &
        ~np.isnan(xgb_prob)
    )

    y_oos = y.iloc[
        np.flatnonzero(valid)
    ].values

    logistic_oos = (
        logistic_prob[valid]
    )

    xgb_oos = (
        xgb_prob[valid]
    )

    if len(np.unique(y_oos)) < 2:
        raise ValueError(
            "OOS sample does not contain "
            "both target classes."
        )

    metrics = {
        "OOS_Observations":
            len(y_oos),

        "OOS_Prevalence":
            float(
                np.mean(y_oos)
            ),

        "Logistic_ROC_AUC":
            roc_auc_score(
                y_oos,
                logistic_oos,
            ),

        "Logistic_PR_AUC":
            average_precision_score(
                y_oos,
                logistic_oos,
            ),

        "XGBoost_ROC_AUC":
            roc_auc_score(
                y_oos,
                xgb_oos,
            ),

        "XGBoost_PR_AUC":
            average_precision_score(
                y_oos,
                xgb_oos,
            ),

        "Folds":
            fold,
    }

    return metrics


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        "============================================\n"
        " 10D OOS SIGNAL IMPORTANCE — LOFO\n"
        " Leave-One-Feature-Out Walk-Forward Test\n"
        "============================================"
    )

    df = load_data()

    start_time = time.time()

    # ========================================================
    # BASELINE — FULL 17 FEATURES
    # ========================================================

    print(
        "\n========== BASELINE: CORE 17F =========="
    )

    baseline = run_walk_forward(
        df,
        FEATURES,
    )

    print(
        f"OOS observations: "
        f"{baseline['OOS_Observations']:,}"
    )

    print(
        f"Logistic ROC: "
        f"{baseline['Logistic_ROC_AUC']:.6f}"
    )

    print(
        f"Logistic PR:  "
        f"{baseline['Logistic_PR_AUC']:.6f}"
    )

    print(
        f"XGBoost ROC:  "
        f"{baseline['XGBoost_ROC_AUC']:.6f}"
    )

    print(
        f"XGBoost PR:   "
        f"{baseline['XGBoost_PR_AUC']:.6f}"
    )

    # ========================================================
    # LOFO
    # ========================================================

    rows = []

    print(
        "\n========== LOFO TESTS =========="
    )

    for i, removed_feature in enumerate(
        FEATURES,
        start=1,
    ):

        print(
            f"\n[{i:02d}/{len(FEATURES)}] "
            f"Remove: {removed_feature}"
        )

        reduced_features = [
            feature
            for feature in FEATURES
            if feature != removed_feature
        ]

        metrics = run_walk_forward(
            df,
            reduced_features,
        )

        # Positive delta means:
        # removing the feature made performance worse.
        #
        # Therefore the removed feature had positive
        # incremental predictive contribution.

        logistic_delta_pr = (
            baseline[
                "Logistic_PR_AUC"
            ]
            -
            metrics[
                "Logistic_PR_AUC"
            ]
        )

        logistic_delta_roc = (
            baseline[
                "Logistic_ROC_AUC"
            ]
            -
            metrics[
                "Logistic_ROC_AUC"
            ]
        )

        xgb_delta_pr = (
            baseline[
                "XGBoost_PR_AUC"
            ]
            -
            metrics[
                "XGBoost_PR_AUC"
            ]
        )

        xgb_delta_roc = (
            baseline[
                "XGBoost_ROC_AUC"
            ]
            -
            metrics[
                "XGBoost_ROC_AUC"
            ]
        )

        row = {
            "Removed_Feature":
                removed_feature,

            "Remaining_Features":
                len(reduced_features),

            "OOS_Observations":
                metrics[
                    "OOS_Observations"
                ],

            "OOS_Prevalence":
                metrics[
                    "OOS_Prevalence"
                ],

            # Logistic
            "Logistic_PR_AUC":
                metrics[
                    "Logistic_PR_AUC"
                ],

            "Logistic_Delta_PR_AUC":
                logistic_delta_pr,

            "Logistic_ROC_AUC":
                metrics[
                    "Logistic_ROC_AUC"
                ],

            "Logistic_Delta_ROC_AUC":
                logistic_delta_roc,

            # XGBoost
            "XGBoost_PR_AUC":
                metrics[
                    "XGBoost_PR_AUC"
                ],

            "XGBoost_Delta_PR_AUC":
                xgb_delta_pr,

            "XGBoost_ROC_AUC":
                metrics[
                    "XGBoost_ROC_AUC"
                ],

            "XGBoost_Delta_ROC_AUC":
                xgb_delta_roc,
        }

        rows.append(row)

        print(
            "  Logistic ΔPR: "
            f"{logistic_delta_pr:+.6f} | "
            "ΔROC: "
            f"{logistic_delta_roc:+.6f}"
        )

        print(
            "  XGBoost  ΔPR: "
            f"{xgb_delta_pr:+.6f} | "
            "ΔROC: "
            f"{xgb_delta_roc:+.6f}"
        )

    results = pd.DataFrame(
        rows
    )

    # ========================================================
    # RANKING
    # ========================================================

    logistic_ranking = (
        results[
            [
                "Removed_Feature",
                "Logistic_Delta_PR_AUC",
                "Logistic_Delta_ROC_AUC",
            ]
        ]
        .sort_values(
            "Logistic_Delta_PR_AUC",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    xgb_ranking = (
        results[
            [
                "Removed_Feature",
                "XGBoost_Delta_PR_AUC",
                "XGBoost_Delta_ROC_AUC",
            ]
        ]
        .sort_values(
            "XGBoost_Delta_PR_AUC",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    logistic_ranking.insert(
        0,
        "Rank",
        np.arange(
            1,
            len(logistic_ranking) + 1,
        ),
    )

    xgb_ranking.insert(
        0,
        "Rank",
        np.arange(
            1,
            len(xgb_ranking) + 1,
        ),
    )

    # ========================================================
    # BASELINE TABLE
    # ========================================================

    baseline_df = pd.DataFrame(
        [
            {
                "Specification":
                    "Core17",

                "Target":
                    TARGET,

                "Purge":
                    PURGE,

                "Features":
                    len(FEATURES),

                **baseline,
            }
        ]
    )

    # ========================================================
    # SAVE
    # ========================================================

    results.to_csv(
        OUTPUT_DIR
        / "lofo_10d_results.csv",
        index=False,
    )

    logistic_ranking.to_csv(
        OUTPUT_DIR
        / "logistic_10d_ranking.csv",
        index=False,
    )

    xgb_ranking.to_csv(
        OUTPUT_DIR
        / "xgboost_10d_ranking.csv",
        index=False,
    )

    baseline_df.to_csv(
        OUTPUT_DIR
        / "baseline_10d.csv",
        index=False,
    )

    # ========================================================
    # PRINT RESULTS
    # ========================================================

    pd.set_option(
        "display.max_columns",
        None,
    )

    pd.set_option(
        "display.width",
        220,
    )

    print(
        "\n"
        "========== LOGISTIC OOS SIGNAL RANKING =========="
    )

    print(
        logistic_ranking
        .round(6)
        .to_string(index=False)
    )

    print(
        "\n"
        "========== XGBOOST OOS SIGNAL RANKING =========="
    )

    print(
        xgb_ranking
        .round(6)
        .to_string(index=False)
    )

    elapsed = (
        time.time()
        - start_time
    )

    print(
        "\n========== INTERPRETATION =========="
    )

    print(
        """
Primary importance metric:
    Delta PR-AUC

Delta PR-AUC =
    Full 17-feature PR-AUC
    minus
    PR-AUC after removing one feature.

Positive Delta:
    Performance became worse when the feature
    was removed.

    -> The feature provided positive unique
       OOS predictive contribution.

Near Zero:
    Removing the feature changed little.

    -> The signal may be redundant with other
       variables.

Negative Delta:
    Performance improved when the feature
    was removed.

    -> The feature may be redundant or noisy
       in this specification.

IMPORTANT:
    This is a diagnostic LOFO analysis.

    It is NOT causal importance.

    It is NOT being used for post-hoc feature
    selection.

    The Core 17-feature specification remains
    locked regardless of these results.
"""
    )

    print(
        "\n========== SAVED =========="
    )

    for filename in [
        "baseline_10d.csv",
        "lofo_10d_results.csv",
        "logistic_10d_ranking.csv",
        "xgboost_10d_ranking.csv",
    ]:
        print(
            OUTPUT_DIR / filename
        )

    print(
        f"\nElapsed: "
        f"{elapsed / 60:.2f} minutes"
    )

    print(
        "\n10D OOS SIGNAL IMPORTANCE COMPLETE"
    )


if __name__ == "__main__":
    main()