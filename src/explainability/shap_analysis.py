import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

from src.config import DATA_FEATURES_DIR, MODELS_DIR


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


FEATURE_COLS = [
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


def main():
    model_path = MODELS_DIR / "xgboost_latest.joblib"
    feature_path = DATA_FEATURES_DIR / "latest_features.csv"

    output_dir = DATA_FEATURES_DIR / "shap"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading 17F XGBoost deployment model.")
    pipeline = joblib.load(model_path)

    scaler = pipeline.named_steps["scaler"]
    classifier = pipeline.named_steps["classifier"]

    logger.info("Loading latest inference features.")
    df = pd.read_csv(
        feature_path,
        index_col="Date",
        parse_dates=True
    ).sort_index()

    missing = [
        col for col in FEATURE_COLS
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing SHAP features: {missing}"
        )

    X = df[FEATURE_COLS].copy()

    # IMPORTANT:
    # XGBoost was trained on StandardScaler-transformed features.
    # SHAP must therefore explain the classifier using the same
    # transformed representation.
    X_scaled = scaler.transform(X)

    X_scaled_df = pd.DataFrame(
        X_scaled,
        index=X.index,
        columns=FEATURE_COLS
    )

    logger.info("Building TreeExplainer.")
    explainer = shap.TreeExplainer(classifier)

    logger.info("Calculating SHAP values.")
    shap_values = explainer.shap_values(X_scaled_df)

    shap_values = np.asarray(shap_values)

    if shap_values.ndim != 2:
        raise ValueError(
            f"Unexpected SHAP shape: {shap_values.shape}"
        )

    # --------------------------------------------------
    # 1. Global SHAP importance
    # --------------------------------------------------

    global_importance = pd.DataFrame({
        "Feature": FEATURE_COLS,
        "Mean_Abs_SHAP": np.abs(shap_values).mean(axis=0)
    }).sort_values(
        "Mean_Abs_SHAP",
        ascending=False
    )

    global_path = output_dir / "global_shap_importance.csv"
    global_importance.to_csv(global_path, index=False)

    # --------------------------------------------------
    # 2. Latest observation SHAP
    # --------------------------------------------------

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

    latest_path = output_dir / "latest_shap.csv"
    latest_df.to_csv(latest_path, index=False)

    # --------------------------------------------------
    # 3. Web/API-friendly JSON
    # --------------------------------------------------

    top_drivers = []

    for _, row in latest_df.head(8).iterrows():
        value = float(row["SHAP_Value"])

        top_drivers.append({
            "feature": row["Feature"],
            "feature_value": float(row["Feature_Value"]),
            "shap_value": value,
            "direction": (
                "risk_up"
                if value > 0
                else "risk_down"
            )
        })

    payload = {
        "date": latest_date.strftime("%Y-%m-%d"),
        "model": "XGBoost",
        "feature_count": len(FEATURE_COLS),
        "top_drivers": top_drivers
    }

    json_path = output_dir / "latest_shap.json"

    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)

    logger.info(
        f"Global SHAP saved: {global_path}"
    )
    logger.info(
        f"Latest SHAP saved: {latest_path}"
    )
    logger.info(
        f"Latest SHAP JSON saved: {json_path}"
    )

    print("\nTOP GLOBAL FEATURES")
    print(global_importance.head(10).to_string(index=False))

    print(f"\nLATEST DATE: {latest_date.date()}")
    print("\nTOP LATEST RISK DRIVERS")
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


if __name__ == "__main__":
    main()
