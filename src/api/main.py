import os
import pandas as pd
import numpy as np
import joblib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.config import DATA_PROCESSED_DIR, DATA_FEATURES_DIR, MODELS_DIR
from src.models.evaluation import ModelEvaluator

app = FastAPI(
    title="U.S. Market Stress Early Warning API",
    description="AI 기반 미국 금융시장 스트레스 조기경보 API",
    version="1.0.0"
)

# CORS 설정 (React/Next.js 프론트엔드 연동)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 데이터 캐시 로더
def load_oos_data():
    path = DATA_PROCESSED_DIR / "oos_predictions.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="OOS predictions file not found. Run walk-forward validation first.")
    df = pd.read_csv(path, index_col='Date', parse_dates=True)
    return df

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Market Stress Early Warning API"}

@app.get("/api/latest")
def get_latest_risk():
    """
    기획서 (PAGE 01 - Market Risk Intelligence 메인 지표)
    가장 최근 날짜의 시장 스트레스 지수 및 10일 위험 확률 반환
    """
    df = load_oos_data()
    latest_row = df.iloc[-1]
    latest_date = df.index[-1].strftime('%Y-%m-%d')
    
    risk_prob = float(latest_row['Prob_XGBoost'])
    msi_score = float(latest_row['MSI'])
    
    # 위험 단계 구분
    if risk_prob >= 0.6:
        status = "HIGH_STRESS"
    elif risk_prob >= 0.3:
        status = "ELEVATED_STRESS"
    else:
        status = "NORMAL"
        
    return {
        "last_updated": latest_date,
        "spy_price": round(float(latest_row['SPY']), 2),
        "vix_level": round(float(latest_row['VIX']), 2),
        "hy_spread": round(float(latest_row['BAA_Treasury_Spread']), 2),
        "market_stress_index": round(msi_score, 3),
        "risk_probability_10d": round(risk_prob * 100, 1),
        "risk_status": status
    }

@app.get("/api/historical")
def get_historical_data(days: int = 1260):
    """
    기획서 (PAGE 01 - 시계열 차트용 데이터)
    최근 N일간의 SPY, VIX, HY Spread, MSI 및 10D 위험확률 제공
    """
    df = load_oos_data()
    if days > 0:
        df = df.iloc[-days:]
        
    chart_data = []
    for date, row in df.iterrows():
        chart_data.append({
            "date": date.strftime('%Y-%m-%d'),
            "spy": round(float(row['SPY']), 2),
            "vix": round(float(row['VIX']), 2),
            "hy_spread": round(float(row['BAA_Treasury_Spread']), 2),
            "msi": round(float(row['MSI']), 3),
            "prob_logistic": round(float(row['Prob_Logistic']) * 100, 1),
            "prob_xgboost": round(float(row['Prob_XGBoost']) * 100, 1),
            "target": int(row['Actual_Target'])
        })
    return {"count": len(chart_data), "data": chart_data}

@app.get("/api/validation")
def get_validation_metrics():
    """
    기획서 (PAGE 02 - Model Validation 화면용 성능 지표 및 위기 사건 분석)
    """
    evaluator = ModelEvaluator()
    overall = evaluator.evaluate_overall().to_dict(orient='records')
    events = evaluator.evaluate_historical_events().to_dict(orient='records')
    
    return {
        "overall_metrics": overall,
        "historical_events": events
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
