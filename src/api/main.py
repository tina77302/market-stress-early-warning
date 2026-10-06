import json
import pandas as pd
import joblib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.config import (
    DATA_PROCESSED_DIR,
    DATA_FEATURES_DIR,
    MODELS_DIR,
)
from src.models.evaluation import ModelEvaluator


app = FastAPI(
    title="U.S. Market Stress Early Warning API",
    description="AI 기반 미국 금융시장 스트레스 조기경보 API",
    version="1.0.0",
)


# ==================================================
# CORS
# ==================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================================================
# Feature whitelist
# 학습 시 사용한 17개 feature와 순서까지 동일해야 함
# ==================================================

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


# ==================================================
# Data loaders
# ==================================================

def load_oos_data():
    """
    Historical walk-forward out-of-sample predictions.
    Used only for historical charts and validation.
    """
    path = DATA_PROCESSED_DIR / "oos_predictions.csv"

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "OOS predictions file not found. "
                "Run walk-forward validation first."
            ),
        )

    return pd.read_csv(
        path,
        index_col="Date",
        parse_dates=True,
    )


def load_latest_features():
    """
    Latest feature observations for current inference.
    Does not require Target_10D to be observable.
    """
    path = DATA_FEATURES_DIR / "latest_features.csv"

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Latest features file not found. "
                "Run feature engineering first."
            ),
        )

    return pd.read_csv(
        path,
        index_col="Date",
        parse_dates=True,
    )


def load_msi_data():
    """
    Market Stress Index series through the latest
    available market observation.
    """
    path = DATA_FEATURES_DIR / "market_stress_index.csv"

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Market stress index file not found. "
                "Run stress index generation first."
            ),
        )

    return pd.read_csv(
        path,
        index_col="Date",
        parse_dates=True,
    )


def load_xgboost_model():
    """
    Deployment XGBoost model fitted on all currently
    labeled training observations.
    """
    path = MODELS_DIR / "xgboost_latest.joblib"

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Saved XGBoost model not found. "
                "Run model training first."
            ),
        )

    return joblib.load(path)


# ==================================================
# Health
# ==================================================

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "Market Stress Early Warning API",
    }


# ==================================================
# PAGE 01 - Current Market Risk
# ==================================================

@app.get("/api/latest")
def get_latest_risk():
    """
    Latest available market observation.

    Current risk is inferred from the latest feature
    vector using the saved deployment XGBoost model.

    The raw model output is reported as a Risk Score,
    not as a calibrated probability.
    """

    feature_df = load_latest_features()

    if feature_df.empty:
        raise HTTPException(
            status_code=500,
            detail="Latest feature dataset is empty.",
        )

    missing_features = [
        col for col in FEATURE_COLS
        if col not in feature_df.columns
    ]

    if missing_features:
        raise HTTPException(
            status_code=500,
            detail=(
                "Missing inference features: "
                + ", ".join(missing_features)
            ),
        )

    latest_row = feature_df.iloc[-1]
    latest_date = feature_df.index[-1]

    # Exact training feature order
    X_latest = feature_df.loc[
        [latest_date],
        FEATURE_COLS,
    ]

    model = load_xgboost_model()

    risk_score = float(
        model.predict_proba(X_latest)[0, 1]
    )

    # Latest MSI should align with latest feature date
    msi_df = load_msi_data()

    if latest_date not in msi_df.index:
        raise HTTPException(
            status_code=500,
            detail=(
                "MSI is unavailable for the latest "
                "feature observation date."
            ),
        )

    msi_score = float(
        msi_df.loc[latest_date, "MSI"]
    )

    return {
        "last_updated": latest_date.strftime("%Y-%m-%d"),
        "spy_price": round(float(latest_row["SPY"]), 2),
        "vix_level": round(float(latest_row["VIX"]), 2),
        "baa_treasury_spread": round(
            float(latest_row["BAA_Treasury_Spread"]),
            3,
        ),
        "market_stress_index": round(msi_score, 3),

        # 0-100 model risk score.
        # Not interpreted as a calibrated probability.
        "risk_score_10d": round(risk_score * 100, 1),

        "risk_score_note": (
            "Higher scores indicate greater model-estimated "
            "risk of a U.S. financial market stress event "
            "within the next 10 trading days. "
            "The score is not a calibrated event probability."
        ),
    }


# ==================================================
# PAGE 01 / PAGE 02 - Historical OOS Data
# ==================================================

@app.get("/api/historical")
def get_historical_data(days: int = 1260):
    """
    Historical walk-forward out-of-sample series.

    Probabilities are exposed publicly as model Risk Scores
    because raw outputs are not treated as calibrated
    event probabilities.
    """

    df = load_oos_data()

    if days > 0:
        df = df.iloc[-days:]

    chart_data = []

    for date, row in df.iterrows():
        chart_data.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "spy": round(float(row["SPY"]), 2),
                "vix": round(float(row["VIX"]), 2),
                "baa_treasury_spread": round(
                    float(row["BAA_Treasury_Spread"]),
                    3,
                ),
                "msi": round(float(row["MSI"]), 3),
                "risk_score_logistic": round(
                    float(row["Prob_Logistic"]) * 100,
                    1,
                ),
                "risk_score_xgboost": round(
                    float(row["Prob_XGBoost"]) * 100,
                    1,
                ),
                "target": int(row["Actual_Target"]),
            }
        )

    return {
        "count": len(chart_data),
        "data": chart_data,
    }
@app.get("/api/multi-horizon-validation")
def get_multi_horizon_validation():
    """
    Precomputed purged walk-forward OOS metrics
    for 1D, 5D, 10D, and 20D forecast horizons.
    """

    path = DATA_PROCESSED_DIR / "multi_horizon_metrics.csv"

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Multi-horizon validation metrics not found. "
                "Run multi-horizon validation first."
            ),
        )

    df = pd.read_csv(path)

    return {
        "count": len(df),
        "data": df.to_dict(orient="records"),
    }

# ==================================================
# PAGE 02 - Model Validation
# ==================================================

@app.get("/api/validation")
def get_validation_metrics():
    """
    Walk-forward OOS model performance and
    historical event analysis.
    """

    evaluator = ModelEvaluator(
     input_filename="oos_predictions_10d.csv"
    )

    overall = (
        evaluator
        .evaluate_overall()
        .to_dict(orient="records")
    )

    events = (
        evaluator
        .evaluate_historical_events()
        .to_dict(orient="records")
    )

    return {
        "overall_metrics": overall,
        "historical_events": events,
    }


# ==================================================
# Local development
# ==================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
    )

# ==================================================
# PAGE 01 - SHAP Risk Drivers
# ==================================================

@app.get("/api/shap")
def get_shap_drivers():
    """
    Latest XGBoost SHAP explanation.

    Positive SHAP values increase the model output;
    negative SHAP values decrease it.

    SHAP values are model-output contributions,
    not percentage-point changes in event probability.
    """

    path = (
        DATA_FEATURES_DIR
        / "shap"
        / "latest_shap.json"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Latest SHAP explanation not found. "
                "Run SHAP analysis first."
            ),
        )

    try:
        with open(path, "r") as f:
            payload = json.load(f)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load SHAP explanation: {exc}",
        )

    return {
        **payload,
        "interpretation_note": (
            "Positive SHAP values push the model risk score "
            "higher and negative values push it lower. "
            "SHAP values are not probability-point changes."
        ),
    }
