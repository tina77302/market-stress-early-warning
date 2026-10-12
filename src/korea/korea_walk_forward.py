import os
import joblib
import numpy as np
import pandas as pd

from src.models.logistic import build_logistic_model
from src.models.xgboost_model import build_xgboost_model


# ============================================================
# Paths
# ============================================================

INPUT_PATH = "data/processed/korea/korea_feature_matrix.csv"

OUTPUT_PATH = (
    "data/processed/korea/"
    "korea_oos_predictions_10d.csv"
)

MODEL_DIR = "models/korea"


# ============================================================
# Validation specification
# ============================================================

TARGET_COL = "Target_10D"

INITIAL_TRAIN_YEARS = 5
TRADING_DAYS_PER_YEAR = 252

MIN_TRAIN_SIZE = (
    INITIAL_TRAIN_YEARS
    * TRADING_DAYS_PER_YEAR
)

STEP_SIZE = 21

# Target_10D(t) uses t+1 ... t+10.
# Therefore the 10 observations immediately before each
# test fold are excluded from training.
PURGE_DAYS = 10


# ============================================================
# Korea 17-feature specification
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


def main():

    print("=" * 78)
    print("KOREA 10D PURGED WALK-FORWARD VALIDATION")
    print("=" * 78)

    # --------------------------------------------------------
    # 1. Load feature matrix
    # --------------------------------------------------------

    df = pd.read_csv(INPUT_PATH)

    df["Date"] = pd.to_datetime(
        df["Date"]
    )

    df = (
        df.sort_values("Date")
        .reset_index(drop=True)
    )

    required_cols = (
        ["Date", TARGET_COL]
        + FEATURE_COLS
        + [
            "Korea_MSI",
            "KOSPI200",
            "VKOSPI",
            "Korea_Credit_Spread",
        ]
    )

    missing_cols = [
        col
        for col in required_cols
        if col not in df.columns
    ]

    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}"
        )

    if df["Date"].duplicated().any():
        raise ValueError(
            "Duplicate dates found."
        )

    if (
        df[FEATURE_COLS]
        .isna()
        .any()
        .any()
    ):
        raise ValueError(
            "Missing values found in ML features."
        )

    print()
    print(
        "Full feature-matrix rows:",
        f"{len(df):,}",
    )

    print(
        "Full range:",
        df["Date"].min().date(),
        "→",
        df["Date"].max().date(),
    )

    print(
        "Number of features:",
        len(FEATURE_COLS),
    )

    # --------------------------------------------------------
    # 2. Separate labeled modeling sample
    #
    # IMPORTANT:
    # Last 10 observations do not yet have observable
    # Target_10D labels.
    #
    # They are NOT converted to zero.
    # They are excluded only from supervised evaluation
    # and deployment-model training.
    # --------------------------------------------------------

    labeled_df = (
        df[
            df[TARGET_COL].notna()
        ]
        .copy()
        .reset_index(drop=True)
    )

    labeled_df[TARGET_COL] = (
        labeled_df[TARGET_COL]
        .astype(int)
    )

    print()
    print(
        "Labeled observations:",
        f"{len(labeled_df):,}",
    )

    print(
        "Labeled range:",
        labeled_df["Date"].min().date(),
        "→",
        labeled_df["Date"].max().date(),
    )

    print(
        "Excluded unlabeled latest rows:",
        f"{len(df) - len(labeled_df):,}",
    )

    print(
        "Target prevalence:",
        f"{labeled_df[TARGET_COL].mean():.4%}",
    )

    if len(labeled_df) <= MIN_TRAIN_SIZE:
        raise ValueError(
            "Not enough labeled observations "
            "for the initial training window."
        )

    # --------------------------------------------------------
    # 3. X / y
    # --------------------------------------------------------

    X = labeled_df[
        FEATURE_COLS
    ].copy()

    y = labeled_df[
        TARGET_COL
    ].copy()

    # --------------------------------------------------------
    # 4. OOS result container
    # --------------------------------------------------------

    results = pd.DataFrame(
        {
            "Date": labeled_df["Date"],
            "Actual_Target": y,
            "Korea_MSI": labeled_df[
                "Korea_MSI"
            ],
            "KOSPI200": labeled_df[
                "KOSPI200"
            ],
            "VKOSPI": labeled_df[
                "VKOSPI"
            ],
            "Korea_Credit_Spread": labeled_df[
                "Korea_Credit_Spread"
            ],
            "Prob_Logistic": np.nan,
            "Prob_XGBoost": np.nan,
        }
    )

    # --------------------------------------------------------
    # 5. Expanding purged walk-forward
    # --------------------------------------------------------

    current_test_start = (
        MIN_TRAIN_SIZE
    )

    fold_count = 0

    print()
    print("-" * 78)
    print("WALK-FORWARD FOLDS")
    print("-" * 78)

    while current_test_start < len(labeled_df):

        test_end = min(
            current_test_start
            + STEP_SIZE,
            len(labeled_df),
        )

        # ----------------------------------------------------
        # Purge
        #
        # Test starts at position s.
        #
        # Target_10D for a training row uses information
        # through t+10.
        #
        # Therefore observations s-10 ... s-1 cannot be
        # included in the training set.
        #
        # iloc[:train_end] is end-exclusive.
        # ----------------------------------------------------

        train_end = (
            current_test_start
            - PURGE_DAYS
        )

        if train_end <= 0:
            raise ValueError(
                "Training window is empty after purge."
            )

        X_train = X.iloc[
            :train_end
        ]

        y_train = y.iloc[
            :train_end
        ]

        X_test = X.iloc[
            current_test_start:test_end
        ]

        y_test = y.iloc[
            current_test_start:test_end
        ]

        if len(X_test) == 0:
            break

        # ----------------------------------------------------
        # Fold QA
        # ----------------------------------------------------

        if y_train.nunique() < 2:
            raise ValueError(
                f"Fold {fold_count + 1}: "
                "training sample contains only one class."
            )

        if (
            X_train.isna()
            .any()
            .any()
        ):
            raise ValueError(
                f"Fold {fold_count + 1}: "
                "training features contain NaN."
            )

        if (
            X_test.isna()
            .any()
            .any()
        ):
            raise ValueError(
                f"Fold {fold_count + 1}: "
                "test features contain NaN."
            )

        neg_count = int(
            (y_train == 0).sum()
        )

        pos_count = int(
            (y_train == 1).sum()
        )

        scale_pos_weight = (
            neg_count
            / (
                pos_count
                + 1e-8
            )
        )

        train_end_date = (
            labeled_df
            .iloc[train_end - 1]["Date"]
            .date()
        )

        test_start_date = (
            labeled_df
            .iloc[current_test_start]["Date"]
            .date()
        )

        test_end_date = (
            labeled_df
            .iloc[test_end - 1]["Date"]
            .date()
        )

        print(
            f"Fold {fold_count + 1:02d} | "
            f"Train={len(X_train):,} | "
            f"Purge={PURGE_DAYS} | "
            f"Test={len(X_test):,} | "
            f"Train End={train_end_date} | "
            f"Test={test_start_date} → {test_end_date} | "
            f"Train Positive={y_train.mean():.2%}"
        )

        # ----------------------------------------------------
        # Logistic Regression
        #
        # Exact same builder used by U.S. model.
        # ----------------------------------------------------

        model_log = (
            build_logistic_model()
        )

        model_log.fit(
            X_train,
            y_train,
        )

        prob_log = (
            model_log
            .predict_proba(
                X_test
            )[:, 1]
        )

        # ----------------------------------------------------
        # XGBoost
        #
        # Exact same builder used by U.S. model.
        # Class weight is recalculated using training data
        # available in each fold only.
        # ----------------------------------------------------

        model_xgb = (
            build_xgboost_model(
                scale_pos_weight=(
                    scale_pos_weight
                )
            )
        )

        model_xgb.fit(
            X_train,
            y_train,
        )

        prob_xgb = (
            model_xgb
            .predict_proba(
                X_test
            )[:, 1]
        )

        # ----------------------------------------------------
        # Store strictly OOS predictions
        # ----------------------------------------------------

        results.loc[
            current_test_start:
            test_end - 1,
            "Prob_Logistic",
        ] = prob_log

        results.loc[
            current_test_start:
            test_end - 1,
            "Prob_XGBoost",
        ] = prob_xgb

        current_test_start = (
            test_end
        )

        fold_count += 1

    # --------------------------------------------------------
    # 6. Strictly OOS sample
    # --------------------------------------------------------

    oos = (
        results.dropna(
            subset=[
                "Prob_Logistic",
                "Prob_XGBoost",
            ]
        )
        .copy()
        .reset_index(drop=True)
    )

    if oos.empty:
        raise ValueError(
            "No OOS predictions were generated."
        )

    print()
    print("=" * 78)
    print("OOS QA")
    print("=" * 78)

    print()
    print(
        "Completed folds:",
        fold_count,
    )

    print(
        "OOS observations:",
        f"{len(oos):,}",
    )

    print(
        "OOS range:",
        oos["Date"].min().date(),
        "→",
        oos["Date"].max().date(),
    )

    print(
        "OOS positive labels:",
        f"{int(oos['Actual_Target'].sum()):,}",
    )

    print(
        "OOS prevalence:",
        f"{oos['Actual_Target'].mean():.4%}",
    )

    print(
        "Missing Logistic predictions:",
        int(
            oos[
                "Prob_Logistic"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Missing XGBoost predictions:",
        int(
            oos[
                "Prob_XGBoost"
            ]
            .isna()
            .sum()
        ),
    )

    # --------------------------------------------------------
    # 7. Save strictly OOS predictions
    # --------------------------------------------------------

    os.makedirs(
        os.path.dirname(
            OUTPUT_PATH
        ),
        exist_ok=True,
    )

    oos.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # 8. Final deployment models
    #
    # IMPORTANT:
    # These models are trained only AFTER OOS evaluation.
    #
    # They use every currently observable labeled row.
    # They are for current website/inference use only.
    #
    # They must NOT be used to report historical OOS
    # validation performance.
    # --------------------------------------------------------

    final_neg = int(
        (y == 0).sum()
    )

    final_pos = int(
        (y == 1).sum()
    )

    final_scale_pos_weight = (
        final_neg
        / (
            final_pos
            + 1e-8
        )
    )

    final_log = (
        build_logistic_model()
    )

    final_log.fit(
        X,
        y,
    )

    final_xgb = (
        build_xgboost_model(
            scale_pos_weight=(
                final_scale_pos_weight
            )
        )
    )

    final_xgb.fit(
        X,
        y,
    )

    os.makedirs(
        MODEL_DIR,
        exist_ok=True,
    )

    joblib.dump(
        final_log,
        os.path.join(
            MODEL_DIR,
            "logistic_10d_latest.joblib",
        ),
    )

    joblib.dump(
        final_xgb,
        os.path.join(
            MODEL_DIR,
            "xgboost_10d_latest.joblib",
        ),
    )

    # --------------------------------------------------------
    # 9. Summary
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print("SAVE COMPLETE")
    print("=" * 78)

    print()
    print(
        "OOS predictions:",
        OUTPUT_PATH,
    )

    print(
        "Logistic deployment model:",
        os.path.join(
            MODEL_DIR,
            "logistic_10d_latest.joblib",
        ),
    )

    print(
        "XGBoost deployment model:",
        os.path.join(
            MODEL_DIR,
            "xgboost_10d_latest.joblib",
        ),
    )

    print()
    print(
        "Validation design:"
    )

    print(
        f"  Initial training = "
        f"{MIN_TRAIN_SIZE:,} observations"
    )

    print(
        f"  Test step = "
        f"{STEP_SIZE} observations"
    )

    print(
        f"  Target horizon = 10 observations"
    )

    print(
        f"  Purge = "
        f"{PURGE_DAYS} observations"
    )

    print(
        "  Window = expanding"
    )

    print(
        "  Models = Logistic Regression + XGBoost"
    )


if __name__ == "__main__":
    main()