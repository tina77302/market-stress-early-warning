from pathlib import Path

import numpy as np
import pandas as pd

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

FEATURE_MATRIX = Path("data/features/feature_matrix.csv")
BREADTH_DATA = Path("data/processed/breadth_qa.csv")

OUTPUT_DIR = Path("data/processed/breadth_ablation")

TARGET = "Target_10D"

MIN_TRAIN_SIZE = 5 * 252
STEP = 21
PURGE = 10
THRESHOLD = 0.5


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


BREADTH_FEATURES = [
    "Breadth_Relative_20D",
    "Breadth_Relative_60D",
    "Breadth_Ratio_252D_ZScore",
]


# ============================================================
# LOAD DATA
# ============================================================

def load_data():

    core = pd.read_csv(
        FEATURE_MATRIX,
        index_col=0,
        parse_dates=True,
    )

    breadth = pd.read_csv(
        BREADTH_DATA,
        index_col=0,
        parse_dates=True,
    )

    breadth = breadth[BREADTH_FEATURES]

    df = core.join(
        breadth,
        how="left",
    )

    required = (
        CORE_FEATURES
        + BREADTH_FEATURES
        + [TARGET]
    )

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    # --------------------------------------------------------
    # COMMON SAMPLE
    # Both 17F and 20F must use exactly the same observations.
    # --------------------------------------------------------

    df = df.dropna(
        subset=required
    ).copy()

    df[TARGET] = df[TARGET].astype(int)

    print("\n========== LOAD DATA ==========")
    print(
        f"Common sample start : {df.index.min().date()}"
    )
    print(
        f"Common sample end   : {df.index.max().date()}"
    )
    print(
        f"Common observations : {len(df):,}"
    )
    print(
        f"Target prevalence   : {df[TARGET].mean():.4%}"
    )

    return df


# ============================================================
# WALK-FORWARD
# ============================================================

def run_walk_forward(
    df,
    feature_cols,
    experiment_name,
):

    X = df[feature_cols]
    y = df[TARGET]

    results = pd.DataFrame(
        index=df.index,
        data={
            "Actual_Target": y,
            "Prob_Logistic": np.nan,
            "Prob_XGBoost": np.nan,
        },
    )

    print(
        f"\n========== {experiment_name} =========="
    )
    print(f"Features : {len(feature_cols)}")

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

        # H-day target:
        # remove final H observations before test period
        # to prevent label overlap.
        train_end = test_start - PURGE

        if train_end <= 0:
            continue

        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]

        X_test = X.iloc[test_start:test_end]

        if len(X_test) == 0:
            continue

        # Safety QA
        if y_train.nunique() < 2:
            continue

        negatives = (y_train == 0).sum()
        positives = (y_train == 1).sum()

        if positives == 0:
            continue

        scale_pos_weight = (
            negatives / positives
        )

        # ----------------------------------------------------
        # EXACT EXISTING PROJECT MODEL BUILDERS
        # ----------------------------------------------------

        logistic = build_logistic_model()

        xgb = build_xgboost_model(
            scale_pos_weight=scale_pos_weight
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
            logistic.predict_proba(X_test)[:, 1]
        )

        xgb_prob = (
            xgb.predict_proba(X_test)[:, 1]
        )

        results.loc[
            X_test.index,
            "Prob_Logistic"
        ] = logistic_prob

        results.loc[
            X_test.index,
            "Prob_XGBoost"
        ] = xgb_prob

        fold += 1

        if fold % 25 == 0:

            print(
                f"Fold {fold:3d} | "
                f"Train end "
                f"{X_train.index[-1].date()} | "
                f"Test "
                f"{X_test.index[0].date()} "
                f"→ "
                f"{X_test.index[-1].date()}"
            )

    results = results.dropna(
        subset=[
            "Prob_Logistic",
            "Prob_XGBoost",
        ]
    )

    print(
        f"\nOOS observations : {len(results):,}"
    )

    print(
        f"OOS period       : "
        f"{results.index.min().date()} "
        f"→ "
        f"{results.index.max().date()}"
    )

    print(
        f"OOS prevalence   : "
        f"{results['Actual_Target'].mean():.4%}"
    )

    return results


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(
    results,
    experiment_name,
):

    rows = []

    y_true = results[
        "Actual_Target"
    ].astype(int)

    for model_name, prob_col in [
        ("Logistic", "Prob_Logistic"),
        ("XGBoost", "Prob_XGBoost"),
    ]:

        prob = results[prob_col]

        pred = (
            prob >= THRESHOLD
        ).astype(int)

        tn, fp, fn, tp = (
            confusion_matrix(
                y_true,
                pred,
                labels=[0, 1],
            ).ravel()
        )

        far = (
            fp / (fp + tn)
            if (fp + tn) > 0
            else np.nan
        )

        missed_rate = (
            fn / (fn + tp)
            if (fn + tp) > 0
            else np.nan
        )

        rows.append({
            "Experiment": experiment_name,
            "Model": model_name,

            "OOS_Observations": len(results),
            "OOS_Prevalence": y_true.mean(),

            "ROC_AUC": roc_auc_score(
                y_true,
                prob,
            ),

            "PR_AUC": average_precision_score(
                y_true,
                prob,
            ),

            "Brier": brier_score_loss(
                y_true,
                prob,
            ),

            "Precision": precision_score(
                y_true,
                pred,
                zero_division=0,
            ),

            "Recall": recall_score(
                y_true,
                pred,
                zero_division=0,
            ),

            "F1": f1_score(
                y_true,
                pred,
                zero_division=0,
            ),

            "FAR": far,
            "Missed_Rate": missed_rate,

            "TP": tp,
            "FP": fp,
            "TN": tn,
            "FN": fn,
        })

    return pd.DataFrame(rows)


# ============================================================
# DELTA
# ============================================================

def calculate_delta(metrics):

    core = (
        metrics[
            metrics["Experiment"]
            == "Core_17F"
        ]
        .set_index("Model")
    )

    breadth = (
        metrics[
            metrics["Experiment"]
            == "Breadth_20F"
        ]
        .set_index("Model")
    )

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

        row = {
            "Model": model
        }

        for metric in metric_cols:

            row[
                f"Delta_{metric}"
            ] = (
                breadth.loc[model, metric]
                - core.loc[model, metric]
            )

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# MAIN
# ============================================================

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = load_data()

    # --------------------------------------------------------
    # CORE 17F
    # --------------------------------------------------------

    core_results = run_walk_forward(
        df=df,
        feature_cols=CORE_FEATURES,
        experiment_name="Core_17F",
    )

    # --------------------------------------------------------
    # CORE 17F + BREADTH 3F
    # --------------------------------------------------------

    breadth_results = run_walk_forward(
        df=df,
        feature_cols=(
            CORE_FEATURES
            + BREADTH_FEATURES
        ),
        experiment_name="Breadth_20F",
    )

    # Exact sample QA
    if not core_results.index.equals(
        breadth_results.index
    ):
        raise RuntimeError(
            "OOS samples differ between "
            "Core 17F and Breadth 20F."
        )

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    core_metrics = calculate_metrics(
        core_results,
        "Core_17F",
    )

    breadth_metrics = calculate_metrics(
        breadth_results,
        "Breadth_20F",
    )

    metrics = pd.concat(
        [
            core_metrics,
            breadth_metrics,
        ],
        ignore_index=True,
    )

    delta = calculate_delta(metrics)

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    metrics.to_csv(
        OUTPUT_DIR
        / "breadth_ablation_metrics.csv",
        index=False,
    )

    delta.to_csv(
        OUTPUT_DIR
        / "breadth_ablation_delta.csv",
        index=False,
    )

    core_results.to_csv(
        OUTPUT_DIR
        / "oos_core_17f.csv"
    )

    breadth_results.to_csv(
        OUTPUT_DIR
        / "oos_breadth_20f.csv"
    )

    # --------------------------------------------------------
    # PRINT
    # --------------------------------------------------------

    pd.set_option(
        "display.max_columns",
        None,
    )

    pd.set_option(
        "display.width",
        200,
    )

    print(
        "\n\n========== FINAL OOS METRICS =========="
    )

    print(
        metrics[
            [
                "Experiment",
                "Model",
                "OOS_Observations",
                "OOS_Prevalence",
                "ROC_AUC",
                "PR_AUC",
                "Brier",
                "Precision",
                "Recall",
                "F1",
                "FAR",
                "Missed_Rate",
            ]
        ].to_string(index=False)
    )

    print(
        "\n\n========== BREADTH FEATURE DELTA =========="
    )

    print(
        delta.to_string(index=False)
    )

    print(
        "\nInterpretation:"
    )

    print(
        "Positive ROC/PR/F1 delta = improvement."
    )

    print(
        "Negative Brier/FAR/Missed delta = improvement."
    )

    print(
        "\nIMPORTANT:"
    )

    print(
        "This experiment does NOT overwrite deployment models."
    )

    print(
        "Breadth features should only be adopted if they "
        "provide consistent incremental OOS value."
    )

    print(
        f"\nSaved metrics → "
        f"{OUTPUT_DIR / 'breadth_ablation_metrics.csv'}"
    )

    print(
        f"Saved delta   → "
        f"{OUTPUT_DIR / 'breadth_ablation_delta.csv'}"
    )

    print(
        "\nBREADTH ABLATION COMPLETE"
    )


if __name__ == "__main__":
    main()