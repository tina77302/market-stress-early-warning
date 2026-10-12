import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "korea"
    / "xgboost_10d_latest.joblib"
)

FEATURE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "korea"
    / "korea_latest_features.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "korea"
    / "shap"
)


# ============================================================
# FINAL KOREA 17 FEATURES
# ============================================================

FEATURE_COLS = [
    "KOSPI200_1D_Return",
    "KOSPI200_5D_Return",
    "KOSPI200_20D_Return",
    "KOSPI200_20D_Vol",
    "KOSPI200_60D_Vol",
    "KOSPI200_Drawdown",
    "KOSPI200_20D_Momentum",

    "VKOSPI_Level",
    "VKOSPI_1D_Change",
    "VKOSPI_5D_Change",
    "VKOSPI_20D_Momentum",
    "VKOSPI_252D_ZScore",

    "Credit_Level",
    "Credit_1D_Change",
    "Credit_5D_Change",
    "Credit_20D_Momentum",
    "Credit_252D_ZScore",
]


def main():

    print("=" * 78)
    print("KOREA XGBOOST SHAP EXPLAINABILITY")
    print("=" * 78)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------
    # 1. Load deployment model
    # --------------------------------------------------------

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Korea XGBoost model not found: {MODEL_PATH}"
        )

    logger.info("Loading Korea 17F XGBoost deployment model.")

    pipeline = joblib.load(MODEL_PATH)

    if "scaler" not in pipeline.named_steps:
        raise ValueError(
            "Expected 'scaler' step in Korea XGBoost pipeline."
        )

    if "classifier" not in pipeline.named_steps:
        raise ValueError(
            "Expected 'classifier' step in Korea XGBoost pipeline."
        )

    scaler = pipeline.named_steps["scaler"]
    classifier = pipeline.named_steps["classifier"]

    # --------------------------------------------------------
    # 2. Load inference features
    # --------------------------------------------------------

    if not FEATURE_PATH.exists():
        raise FileNotFoundError(
            f"Korea latest feature file not found: {FEATURE_PATH}"
        )

    logger.info("Loading Korea inference features.")

    df = pd.read_csv(
        FEATURE_PATH,
        index_col="Date",
        parse_dates=True
    ).sort_index()

    missing = [
        col
        for col in FEATURE_COLS
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing Korea SHAP features: {missing}"
        )

    X = df[FEATURE_COLS].copy()

    if X.empty:
        raise ValueError(
            "Korea SHAP feature matrix is empty."
        )

    if X.isna().any().any():
        missing_counts = X.isna().sum()
        missing_counts = missing_counts[
            missing_counts > 0
        ]

        raise ValueError(
            "Missing values detected in Korea SHAP features:\n"
            f"{missing_counts}"
        )

    print()
    print(f"Observations explained: {len(X):,}")
    print(
        "Date range: "
        f"{X.index.min().date()} → "
        f"{X.index.max().date()}"
    )
    print(f"Number of features: {len(FEATURE_COLS)}")

    # --------------------------------------------------------
    # 3. Apply same scaler used during model training
    # --------------------------------------------------------

    # IMPORTANT:
    # The Korea XGBoost classifier was trained on
    # StandardScaler-transformed features.
    #
    # SHAP therefore explains the classifier using exactly
    # the same transformed representation.
    #
    # Raw feature values are retained separately for
    # human-readable output.

    X_scaled = scaler.transform(X)

    X_scaled_df = pd.DataFrame(
        X_scaled,
        index=X.index,
        columns=FEATURE_COLS
    )

    # --------------------------------------------------------
    # 4. Tree SHAP
    # --------------------------------------------------------

    logger.info("Building Korea TreeExplainer.")

    explainer = shap.TreeExplainer(
        classifier
    )

    logger.info("Calculating Korea SHAP values.")

    shap_values = explainer.shap_values(
        X_scaled_df
    )

    shap_values = np.asarray(
        shap_values
    )

    if shap_values.ndim != 2:
        raise ValueError(
            "Unexpected Korea SHAP shape: "
            f"{shap_values.shape}"
        )

    if shap_values.shape != X_scaled_df.shape:
        raise ValueError(
            "SHAP matrix shape does not match "
            "the feature matrix. "
            f"SHAP={shap_values.shape}, "
            f"X={X_scaled_df.shape}"
        )

    # ========================================================
    # 5. GLOBAL SHAP IMPORTANCE
    # ========================================================

    global_importance = pd.DataFrame({
        "Feature": FEATURE_COLS,
        "Mean_Abs_SHAP": (
            np.abs(shap_values).mean(axis=0)
        )
    }).sort_values(
        "Mean_Abs_SHAP",
        ascending=False
    )

    global_path = (
        OUTPUT_DIR
        / "global_shap_importance.csv"
    )

    global_importance.to_csv(
        global_path,
        index=False
    )

    # ========================================================
    # 6. LATEST OBSERVATION SHAP
    # ========================================================

    latest_date = X.index[-1]

    latest_raw = X.iloc[-1]

    latest_shap = shap_values[-1]

    latest_df = pd.DataFrame({
        "Feature": FEATURE_COLS,
        "Feature_Value": latest_raw.values,
        "SHAP_Value": latest_shap,
        "Abs_SHAP": np.abs(latest_shap)
    }).sort_values(
        "Abs_SHAP",
        ascending=False
    )

    latest_path = (
        OUTPUT_DIR
        / "latest_shap.csv"
    )

    latest_df.to_csv(
        latest_path,
        index=False
    )

    # ========================================================
    # 7. WEB / API FRIENDLY JSON
    # ========================================================

    top_drivers = []

    for _, row in latest_df.head(8).iterrows():

        shap_value = float(
            row["SHAP_Value"]
        )

        top_drivers.append({
            "feature": row["Feature"],
            "feature_value": float(
                row["Feature_Value"]
            ),
            "shap_value": shap_value,
            "direction": (
                "risk_up"
                if shap_value > 0
                else "risk_down"
            )
        })

    payload = {
        "date": latest_date.strftime(
            "%Y-%m-%d"
        ),
        "market": "Korea",
        "model": "XGBoost",
        "target_horizon": "10D",
        "feature_count": len(
            FEATURE_COLS
        ),
        "top_drivers": top_drivers
    }

    json_path = (
        OUTPUT_DIR
        / "latest_shap.json"
    )

    with open(
        json_path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False
        )

    # ========================================================
    # 8. QA / OUTPUT
    # ========================================================

    print()
    print("=" * 78)
    print("TOP GLOBAL KOREA FEATURES")
    print("=" * 78)
    print()

    print(
        global_importance
        .head(10)
        .to_string(index=False)
    )

    print()
    print("=" * 78)
    print("LATEST KOREA RISK DRIVERS")
    print("=" * 78)
    print()

    print(
        f"Latest date: "
        f"{latest_date.date()}"
    )

    print()

    print(
        latest_df[
            [
                "Feature",
                "Feature_Value",
                "SHAP_Value"
            ]
        ]
        .head(8)
        .to_string(index=False)
    )

    print()
    print("=" * 78)
    print("SAVE COMPLETE")
    print("=" * 78)
    print()

    print(
        f"Global SHAP: {global_path}"
    )
    print(
        f"Latest SHAP: {latest_path}"
    )
    print(
        f"Latest SHAP JSON: {json_path}"
    )

    print()
    print("Interpretation:")
    print(
        "- Mean |SHAP| measures fitted-model "
        "output importance."
    )
    print(
        "- Positive SHAP values push the "
        "XGBoost model output toward higher risk."
    )
    print(
        "- Negative SHAP values push the "
        "model output toward lower risk."
    )
    print(
        "- SHAP values are model-output "
        "contributions, not percentage-point "
        "changes in real-world stress probability."
    )
    print(
        "- Global SHAP is not an OOS "
        "incremental predictive-value test."
    )


if __name__ == "__main__":
    main()