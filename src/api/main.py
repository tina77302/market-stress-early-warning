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

# ==================================================
# KOREA - Configuration
# ==================================================

KOREA_PROCESSED_DIR = (
    DATA_PROCESSED_DIR / "korea"
)

KOREA_MODEL_DIR = (
    MODELS_DIR.parent / "korea"
)


KOREA_FEATURE_COLS = [
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


# ==================================================
# KOREA - Data loaders
# ==================================================

def load_korea_latest_features():
    """
    Korea feature observations through the latest
    available market date.

    The latest row is used for current inference.
    """

    path = (
        KOREA_PROCESSED_DIR
        / "korea_latest_features.csv"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Korea latest features file not found. "
                "Run Korea feature engineering first."
            ),
        )

    return pd.read_csv(
        path,
        index_col="Date",
        parse_dates=True,
    )


def load_korea_msi_data():
    """
    Korea Market Stress Index through the latest
    available market observation.
    """

    path = (
        KOREA_PROCESSED_DIR
        / "korea_stress_index.csv"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Korea stress index file not found. "
                "Run Korea stress index generation first."
            ),
        )

    return pd.read_csv(
        path,
        index_col="Date",
        parse_dates=True,
    )


def load_korea_xgboost_model():
    """
    Korea deployment XGBoost model fitted on all
    currently labeled Korea training observations.
    """

    path = (
        KOREA_MODEL_DIR
        / "xgboost_10d_latest.joblib"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Korea XGBoost deployment model not found. "
                "Run Korea walk-forward training first."
            ),
        )

    return joblib.load(
        path
    )


# ==================================================
# KOREA - Current Market Risk
# ==================================================

@app.get("/api/korea/latest")
def get_korea_latest_risk():
    """
    Latest available Korea market observation.

    The Korea 10D Risk Score is generated from the
    latest 17-feature vector using the saved Korea
    XGBoost deployment model.

    The model output is reported as a Risk Score,
    not as a calibrated event probability.
    """

    feature_df = (
        load_korea_latest_features()
    )

    if feature_df.empty:
        raise HTTPException(
            status_code=500,
            detail=(
                "Korea latest feature dataset is empty."
            ),
        )

    missing_features = [
        col
        for col in KOREA_FEATURE_COLS
        if col not in feature_df.columns
    ]

    if missing_features:
        raise HTTPException(
            status_code=500,
            detail=(
                "Missing Korea inference features: "
                + ", ".join(missing_features)
            ),
        )

    latest_row = (
        feature_df.iloc[-1]
    )

    latest_date = (
        feature_df.index[-1]
    )

    # Exact training feature order
    X_latest = feature_df.loc[
        [latest_date],
        KOREA_FEATURE_COLS,
    ]

    model = (
        load_korea_xgboost_model()
    )

    risk_score = float(
        model.predict_proba(
            X_latest
        )[0, 1]
    )

    # --------------------------------------------------
    # Latest Korea MSI must align with inference date.
    # --------------------------------------------------

    msi_df = (
        load_korea_msi_data()
    )

    if latest_date not in msi_df.index:
        raise HTTPException(
            status_code=500,
            detail=(
                "Korea MSI is unavailable for the latest "
                "feature observation date."
            ),
        )

    msi_row = (
        msi_df.loc[latest_date]
    )

    korea_msi = float(
        msi_row["Korea_MSI"]
    )

    stress_threshold = float(
        msi_row["Stress_Threshold"]
    )

    is_stress_event = bool(
        int(msi_row["Is_Stress_Event"])
    )

    return {
        "market": "South Korea",

        "last_updated":
            latest_date.strftime(
                "%Y-%m-%d"
            ),

        "kospi200": round(
            float(
                latest_row["KOSPI200"]
            ),
            2,
        ),

        "vkospi": round(
            float(
                latest_row["VKOSPI"]
            ),
            2,
        ),

        "korea_credit_spread": round(
            float(
                latest_row[
                    "Korea_Credit_Spread"
                ]
            ),
            3,
        ),

        "korea_credit_spread_bp": round(
            float(
                latest_row[
                    "Korea_Credit_Spread"
                ]
            )
            * 100,
            1,
        ),

        "market_stress_index": round(
            korea_msi,
            3,
        ),

        "stress_threshold": round(
            stress_threshold,
            3,
        ),

        "is_stress_event":
            is_stress_event,

        # 0-100 model Risk Score.
        # Not interpreted as a calibrated probability.
        "risk_score_10d": round(
            risk_score * 100,
            1,
        ),

        "warning_threshold": 50.0,

        "warning_active": bool(
            risk_score >= 0.50
        ),

        "risk_score_note": (
            "Higher scores indicate greater model-estimated "
            "risk of a South Korean financial market stress "
            "event within the next 10 trading days. "
            "The score is not a calibrated event probability."
        ),

        "stress_event_note": (
            "The current Stress Event state is based on "
            "whether Korea MSI reaches or exceeds its "
            "past-only expanding 90th-percentile threshold."
        ),
    }
    
# ==================================================
# KOREA - SHAP Risk Drivers
# ==================================================

@app.get("/api/korea/shap")
def get_korea_shap_drivers():
    """
    Latest Korea XGBoost SHAP explanation.

    Positive SHAP values increase the model output;
    negative SHAP values decrease it.

    SHAP values are model-output contributions,
    not percentage-point changes in event probability.
    """

    path = (
        KOREA_PROCESSED_DIR
        / "shap"
        / "latest_shap.json"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Latest Korea SHAP explanation not found. "
                "Run Korea SHAP analysis first."
            ),
        )

    try:
        with open(path, "r") as f:
            payload = json.load(f)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Failed to load Korea SHAP explanation: {exc}"
            ),
        )

    return {
        **payload,
        "interpretation_note": (
            "Positive SHAP values push the Korea model "
            "risk score higher and negative values push "
            "it lower. SHAP values are model-output "
            "contributions, not probability-point changes."
        ),
    }
    
# ==================================================
# KOREA - Historical OOS Data
# ==================================================

@app.get("/api/korea/historical")
def get_korea_historical_data(days: int = 1260):
    """
    Historical Korea purged walk-forward
    out-of-sample predictions.

    Model outputs are exposed as Risk Scores,
    not calibrated event probabilities.
    """

    path = (
        KOREA_PROCESSED_DIR
        / "korea_oos_predictions_10d.csv"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Korea OOS predictions file not found. "
                "Run Korea walk-forward validation first."
            ),
        )

    df = pd.read_csv(
        path,
        index_col="Date",
        parse_dates=True,
    )

    if days > 0:
        df = df.iloc[-days:]

    chart_data = []

    for date, row in df.iterrows():
        chart_data.append(
            {
                "date": date.strftime("%Y-%m-%d"),

                "kospi200": round(
                    float(row["KOSPI200"]),
                    2,
                ),

                "vkospi": round(
                    float(row["VKOSPI"]),
                    2,
                ),

                "korea_credit_spread": round(
                    float(row["Korea_Credit_Spread"]),
                    3,
                ),

                "korea_credit_spread_bp": round(
                    float(row["Korea_Credit_Spread"]) * 100,
                    1,
                ),

                "msi": round(
                    float(row["Korea_MSI"]),
                    3,
                ),

                "risk_score_logistic": round(
                    float(row["Prob_Logistic"]) * 100,
                    1,
                ),

                "risk_score_xgboost": round(
                    float(row["Prob_XGBoost"]) * 100,
                    1,
                ),

                "target": int(
                    row["Actual_Target"]
                ),
            }
        )

    return {
        "market": "South Korea",
        "forecast_horizon": "10D",
        "data_type": "purged_walk_forward_oos",
        "count": len(chart_data),
        "data": chart_data,
    }
    
# ==================================================
# KOREA - Model Validation
# ==================================================

@app.get("/api/korea/validation")
def get_korea_validation():
    """
    Korea 10D purged walk-forward out-of-sample
    model validation metrics.

    Threshold-based metrics use the fixed
    0.50 reference warning cutoff.
    """

    path = (
        KOREA_PROCESSED_DIR
        / "korea_model_evaluation_10d.csv"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Korea model evaluation file not found. "
                "Run Korea model evaluation first."
            ),
        )

    df = pd.read_csv(path)

    metrics = []

    for _, row in df.iterrows():
        metrics.append(
            {
                "model": str(row["Model"]),

                "roc_auc": round(
                    float(row["ROC-AUC"]),
                    6,
                ),

                "pr_auc": round(
                    float(row["PR-AUC (AP)"]),
                    6,
                ),

                "brier_score": round(
                    float(row["Brier Score"]),
                    6,
                ),

                "threshold": round(
                    float(row["Threshold"]),
                    2,
                ),

                "tp": int(row["TP"]),
                "fp": int(row["FP"]),
                "tn": int(row["TN"]),
                "fn": int(row["FN"]),

                "precision": round(
                    float(row["Precision"]),
                    6,
                ),

                "recall": round(
                    float(row["Recall"]),
                    6,
                ),

                "f1": round(
                    float(row["F1"]),
                    6,
                ),

                "false_alarm_rate": round(
                    float(row["False Alarm Rate"]),
                    6,
                ),

                "missed_event_rate": round(
                    float(row["Missed Event Rate"]),
                    6,
                ),
            }
        )

    return {
        "market": "South Korea",
        "forecast_horizon": "10D",
        "validation_method":
            "Purged expanding walk-forward OOS",

        "oos_start": "2016-09-13",
        "oos_end": "2026-09-16",

        "oos_observations": 2454,
        "positive_observations": 617,
        "target_prevalence": 0.251426,

        "warning_threshold": 0.50,

        "models": metrics,

        "interpretation_note": (
            "Metrics are based on purged expanding "
            "walk-forward out-of-sample predictions. "
            "The 0.50 threshold is a fixed reference "
            "warning cutoff and was not selected "
            "post-hoc from OOS results."
        ),
    }