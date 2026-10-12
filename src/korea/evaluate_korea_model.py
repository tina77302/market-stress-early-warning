import os
import numpy as np
import pandas as pd

from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    brier_score_loss,
)


# ============================================================
# Paths / specification
# ============================================================

INPUT_PATH = (
    "data/processed/korea/"
    "korea_oos_predictions_10d.csv"
)

OUTPUT_PATH = (
    "data/processed/korea/"
    "korea_model_evaluation_10d.csv"
)

DEFAULT_THRESHOLD = 0.50


# ============================================================
# Binary metrics
# ============================================================

def calculate_binary_metrics(
    y_true,
    y_prob,
    threshold,
):

    y_pred = (
        y_prob >= threshold
    ).astype(int)

    tn, fp, fn, tp = confusion_matrix(
        y_true,
        y_pred,
        labels=[0, 1],
    ).ravel()

    precision = precision_score(
        y_true,
        y_pred,
        zero_division=0,
    )

    recall = recall_score(
        y_true,
        y_pred,
        zero_division=0,
    )

    f1 = f1_score(
        y_true,
        y_pred,
        zero_division=0,
    )

    false_alarm_rate = (
        fp / (fp + tn)
        if (fp + tn) > 0
        else np.nan
    )

    missed_event_rate = (
        fn / (fn + tp)
        if (fn + tp) > 0
        else np.nan
    )

    return {
        "Threshold": threshold,
        "TP": int(tp),
        "FP": int(fp),
        "TN": int(tn),
        "FN": int(fn),
        "Precision": precision,
        "Recall": recall,
        "F1": f1,
        "False Alarm Rate": false_alarm_rate,
        "Missed Event Rate": missed_event_rate,
    }


# ============================================================
# Main evaluation
# ============================================================

def main():

    print("=" * 78)
    print("KOREA 10D STRICTLY OOS MODEL EVALUATION")
    print("=" * 78)

    # --------------------------------------------------------
    # 1. Load strictly OOS predictions
    # --------------------------------------------------------

    df = pd.read_csv(
        INPUT_PATH,
        parse_dates=["Date"],
    )

    df = (
        df.sort_values("Date")
        .reset_index(drop=True)
    )

    required_cols = [
        "Date",
        "Actual_Target",
        "Prob_Logistic",
        "Prob_XGBoost",
        "Korea_MSI",
        "KOSPI200",
        "VKOSPI",
        "Korea_Credit_Spread",
    ]

    missing_cols = [
        col
        for col in required_cols
        if col not in df.columns
    ]

    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}"
        )

    if df.empty:
        raise ValueError(
            "OOS prediction dataset is empty."
        )

    if df["Date"].duplicated().any():
        raise ValueError(
            "Duplicate dates found in OOS predictions."
        )

    prediction_cols = [
        "Prob_Logistic",
        "Prob_XGBoost",
    ]

    if (
        df[prediction_cols]
        .isna()
        .any()
        .any()
    ):
        raise ValueError(
            "Missing OOS probabilities found."
        )

    if (
        (df[prediction_cols] < 0)
        | (df[prediction_cols] > 1)
    ).any().any():
        raise ValueError(
            "Predicted probabilities outside [0, 1]."
        )

    y_true = (
        df["Actual_Target"]
        .astype(int)
    )

    unique_targets = set(
        y_true.unique()
    )

    if not unique_targets.issubset(
        {0, 1}
    ):
        raise ValueError(
            "Actual_Target must contain only 0 and 1."
        )

    if y_true.nunique() < 2:
        raise ValueError(
            "OOS target contains only one class."
        )

    prevalence = (
        y_true.mean()
    )

    # --------------------------------------------------------
    # 2. Dataset QA
    # --------------------------------------------------------

    print()
    print("OOS Period:")
    print(
        " ",
        df["Date"].min().date(),
        "→",
        df["Date"].max().date(),
    )

    print(
        "OOS Observations:",
        f"{len(df):,}",
    )

    print(
        "Positive Targets:",
        f"{int(y_true.sum()):,}",
    )

    print(
        "Target Prevalence:",
        f"{prevalence:.4%}",
    )

    print(
        "Reference Threshold:",
        f"{DEFAULT_THRESHOLD:.2f}",
    )

    # --------------------------------------------------------
    # 3. Evaluate models
    # --------------------------------------------------------

    models = {
        "Logistic Regression":
            df["Prob_Logistic"],

        "XGBoost":
            df["Prob_XGBoost"],
    }

    results = []

    for model_name, y_prob in models.items():

        roc_auc = roc_auc_score(
            y_true,
            y_prob,
        )

        # Same definition as the U.S. evaluation:
        # Average Precision is reported as PR-AUC (AP).
        pr_auc = average_precision_score(
            y_true,
            y_prob,
        )

        brier = brier_score_loss(
            y_true,
            y_prob,
        )

        binary = (
            calculate_binary_metrics(
                y_true,
                y_prob,
                DEFAULT_THRESHOLD,
            )
        )

        results.append(
            {
                "Model": model_name,
                "ROC-AUC": roc_auc,
                "PR-AUC (AP)": pr_auc,
                "Brier Score": brier,
                **binary,
            }
        )

    result_df = pd.DataFrame(
        results
    )

    # --------------------------------------------------------
    # 4. Print results
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print("OVERALL OOS PERFORMANCE")
    print("=" * 78)
    print()

    print(
        result_df
        .round(6)
        .to_string(index=False)
    )

    # --------------------------------------------------------
    # 5. Threshold sensitivity
    #
    # DIAGNOSTIC ONLY.
    # Never use the OOS table to choose a threshold.
    # --------------------------------------------------------

    thresholds = [
        0.30,
        0.40,
        0.50,
        0.60,
        0.70,
    ]

    threshold_rows = []

    for model_name, y_prob in models.items():

        for threshold in thresholds:

            metrics = (
                calculate_binary_metrics(
                    y_true,
                    y_prob,
                    threshold,
                )
            )

            threshold_rows.append(
                {
                    "Model": model_name,
                    **metrics,
                }
            )

    threshold_df = pd.DataFrame(
        threshold_rows
    )

    print()
    print("=" * 78)
    print(
        "THRESHOLD SENSITIVITY "
        "(DIAGNOSTIC ONLY — NOT FOR OOS TUNING)"
    )
    print("=" * 78)
    print()

    print(
        threshold_df
        .round(6)
        .to_string(index=False)
    )

    # --------------------------------------------------------
    # 6. Save official 0.50-reference evaluation
    # --------------------------------------------------------

    os.makedirs(
        os.path.dirname(
            OUTPUT_PATH
        ),
        exist_ok=True,
    )

    result_df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("=" * 78)
    print("SAVE COMPLETE")
    print("=" * 78)

    print()
    print(
        "Evaluation saved to:",
        OUTPUT_PATH,
    )

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "  ROC-AUC and PR-AUC are "
        "threshold-independent."
    )

    print(
        "  Precision / Recall / F1 / FAR / "
        "Missed Rate use the fixed 0.50 "
        "reference threshold."
    )

    print(
        "  The threshold sensitivity table "
        "is diagnostic only."
    )

    print(
        "  No threshold is selected using "
        "the OOS test results."
    )


if __name__ == "__main__":
    main()