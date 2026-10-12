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

FEATURE_PATH = Path(
    "data/processed/korea/korea_feature_matrix.csv"
)

OUTPUT_DIR = Path(
    "data/processed/korea/oos_signal_importance"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

TARGET = "Target_10D"

# Keep the validation design identical to the
# official Korea 10D walk-forward evaluation.
MIN_TRAIN_SIZE = 5 * 252
STEP = 21
PURGE = 10


# ============================================================
# LOCKED KOREA CORE 17 FEATURES
# ============================================================

FEATURES = [
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

    # Korea Credit Spread
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
        "\n========== LOAD KOREA DATA =========="
    )

    if not FEATURE_PATH.exists():
        raise FileNotFoundError(
            f"Korea feature matrix not found: "
            f"{FEATURE_PATH}"
        )

    df = pd.read_csv(
        FEATURE_PATH,
        index_col=0,
        parse_dates=True,
    )

    df.index = pd.to_datetime(
        df.index
    )

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

    # --------------------------------------------------------
    # The latest 10 observations do not yet have a known
    # forward 10-trading-day outcome.
    #
    # They must remain excluded from OOS validation rather
    # than being converted to negative labels.
    # --------------------------------------------------------

    df = df.dropna(
        subset=[TARGET]
    ).copy()

    # --------------------------------------------------------
    # Feature QA
    # --------------------------------------------------------

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
        f"Target positives: "
        f"{int(df[TARGET].sum()):,}"
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
# PURGED WALK-FORWARD OOS
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

        # ----------------------------------------------------
        # 10D label-overlap purge
        #
        # Target_10D at time t uses observations
        # t+1 through t+10.
        #
        # Therefore the final 10 observations immediately
        # before each OOS test window are excluded from
        # training.
        #
        # iloc end is exclusive:
        #
        # train_end = test_start - 10
        # X.iloc[:train_end]
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Logistic Regression
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # XGBoost
        # ----------------------------------------------------

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

    valid_positions = np.flatnonzero(
        valid
    )

    y_oos = y.iloc[
        valid_positions
    ].values

    logistic_oos = (
        logistic_prob[valid]
    )

    xgb_oos = (
        xgb_prob[valid]
    )

    if len(y_oos) == 0:
        raise ValueError(
            "No OOS predictions were generated."
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
        "==================================================\n"
        " KOREA 10D OOS SIGNAL IMPORTANCE — LOFO\n"
        " Leave-One-Feature-Out Purged Walk-Forward Test\n"
        "=================================================="
    )

    df = load_data()

    start_time = time.time()

    # ========================================================
    # BASELINE — FULL KOREA 17 FEATURES
    # ========================================================

    print(
        "\n"
        "========== BASELINE: KOREA CORE 17F =========="
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
        f"OOS prevalence: "
        f"{baseline['OOS_Prevalence']:.4%}"
    )

    print(
        f"Folds: "
        f"{baseline['Folds']}"
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

    # --------------------------------------------------------
    # Critical reproducibility QA
    #
    # These baseline values should reproduce the official
    # Korea 10D OOS evaluation:
    #
    # Logistic ROC = 0.864020
    # Logistic PR  = 0.749168
    # XGBoost ROC  = 0.879654
    # XGBoost PR   = 0.741549
    # OOS N        = 2,454
    # --------------------------------------------------------

    expected = {
        "OOS_Observations": 2454,
        "Logistic_ROC_AUC": 0.864020,
        "Logistic_PR_AUC": 0.749168,
        "XGBoost_ROC_AUC": 0.879654,
        "XGBoost_PR_AUC": 0.741549,
    }

    tolerance = 1e-6

    if (
        baseline["OOS_Observations"]
        != expected["OOS_Observations"]
    ):
        raise ValueError(
            "LOFO baseline OOS sample does not match "
            "the official Korea 10D evaluation. "
            f"Expected "
            f"{expected['OOS_Observations']:,}, "
            f"got "
            f"{baseline['OOS_Observations']:,}."
        )

    for metric in [
        "Logistic_ROC_AUC",
        "Logistic_PR_AUC",
        "XGBoost_ROC_AUC",
        "XGBoost_PR_AUC",
    ]:

        difference = abs(
            baseline[metric]
            - expected[metric]
        )

        if difference > tolerance:
            raise ValueError(
                "LOFO baseline does not reproduce "
                "the official Korea 10D evaluation. "
                f"{metric}: "
                f"expected {expected[metric]:.6f}, "
                f"got {baseline[metric]:.6f}"
            )

    print()
    print(
        "Baseline reproducibility QA: PASS"
    )

    # ========================================================
    # LOFO
    # ========================================================

    rows = []

    print(
        "\n========== KOREA LOFO TESTS =========="
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

        # ----------------------------------------------------
        # Positive delta:
        #
        # Full-model metric
        # minus
        # reduced-model metric
        #
        # If positive, performance became worse after
        # removing the feature.
        #
        # Therefore the feature provided positive
        # incremental OOS predictive contribution,
        # conditional on the remaining features.
        # ----------------------------------------------------

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

            "Folds":
                metrics[
                    "Folds"
                ],
        }

        rows.append(
            row
        )

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
        .reset_index(
            drop=True
        )
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
        .reset_index(
            drop=True
        )
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
                    "Korea_Core17",

                "Target":
                    TARGET,

                "Purge":
                    PURGE,

                "Initial_Train":
                    MIN_TRAIN_SIZE,

                "Step":
                    STEP,

                "Features":
                    len(FEATURES),

                **baseline,
            }
        ]
    )

    # ========================================================
    # SAVE
    # ========================================================

    results_path = (
        OUTPUT_DIR
        / "lofo_10d_results.csv"
    )

    logistic_path = (
        OUTPUT_DIR
        / "logistic_10d_ranking.csv"
    )

    xgb_path = (
        OUTPUT_DIR
        / "xgboost_10d_ranking.csv"
    )

    baseline_path = (
        OUTPUT_DIR
        / "baseline_10d.csv"
    )

    results.to_csv(
        results_path,
        index=False,
    )

    logistic_ranking.to_csv(
        logistic_path,
        index=False,
    )

    xgb_ranking.to_csv(
        xgb_path,
        index=False,
    )

    baseline_df.to_csv(
        baseline_path,
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
        .to_string(
            index=False
        )
    )

    print(
        "\n"
        "========== XGBOOST OOS SIGNAL RANKING =========="
    )

    print(
        xgb_ranking
        .round(6)
        .to_string(
            index=False
        )
    )

    elapsed = (
        time.time()
        - start_time
    )

    # ========================================================
    # INTERPRETATION
    # ========================================================

    print(
        "\n========== INTERPRETATION =========="
    )

    print(
        """
Primary importance metric:
    Delta PR-AUC

Delta PR-AUC =
    Full Korea 17-feature PR-AUC
    minus
    PR-AUC after removing one feature.

Positive Delta:
    Performance became worse when the feature
    was removed.

    -> The feature provided positive unique
       OOS predictive contribution conditional
       on the remaining features.

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

    The Korea Core 17-feature specification
    remains locked regardless of these results.

    SHAP and LOFO answer different questions:
    SHAP describes fitted-model output
    contribution.

    LOFO measures incremental OOS predictive
    information conditional on the remaining
    features.
"""
    )

    # ========================================================
    # SAVED
    # ========================================================

    print(
        "\n========== SAVED =========="
    )

    for path in [
        baseline_path,
        results_path,
        logistic_path,
        xgb_path,
    ]:
        print(
            path
        )

    print(
        f"\nElapsed: "
        f"{elapsed / 60:.2f} minutes"
    )

    print(
        "\n"
        "KOREA 10D OOS SIGNAL IMPORTANCE COMPLETE"
    )


if __name__ == "__main__":
    main()