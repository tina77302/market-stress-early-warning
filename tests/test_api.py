import json

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import src.api.main as api
from src.models.xgboost_model import build_xgboost_model
from tests.conftest import FEATURE_COLS, make_oos_predictions


@pytest.fixture
def client(data_dirs):
    return TestClient(api.app)


def test_feature_whitelist_matches_training_order():
    assert api.FEATURE_COLS == FEATURE_COLS


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/latest",
        "/api/historical",
        "/api/shap",
        "/api/multi-horizon-validation",
        "/api/korea/latest",
    ],
)
def test_missing_artifacts_return_404(client, endpoint, monkeypatch, tmp_path):
    monkeypatch.setattr(api, "KOREA_PROCESSED_DIR", tmp_path / "korea")
    r = client.get(endpoint)
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_historical_respects_days_and_scales_scores(client, data_dirs):
    df = make_oos_predictions(n=100)
    df.to_csv(data_dirs.DATA_PROCESSED_DIR / "oos_predictions.csv")

    r = client.get("/api/historical", params={"days": 30})
    assert r.status_code == 200
    body = r.json()

    assert body["count"] == 30
    assert len(body["data"]) == 30
    last = body["data"][-1]
    assert last["date"] == df.index[-1].strftime("%Y-%m-%d")
    assert last["risk_score_xgboost"] == pytest.approx(
        round(df["Prob_XGBoost"].iloc[-1] * 100, 1)
    )
    assert last["target"] in (0, 1)

    full = client.get("/api/historical", params={"days": 0}).json()
    assert full["count"] == 100


def test_latest_risk_uses_saved_model(client, feature_pipeline):
    dirs = feature_pipeline.dirs
    fm = feature_pipeline.features.dropna(subset=["Target_10D"])

    model = build_xgboost_model()
    model.fit(fm[FEATURE_COLS], fm["Target_10D"].astype(int))
    joblib.dump(model, dirs.MODELS_DIR / "xgboost_latest.joblib")

    latest = pd.read_csv(
        dirs.DATA_FEATURES_DIR / "latest_features.csv", index_col="Date", parse_dates=True
    )
    expected = float(model.predict_proba(latest.iloc[[-1]][FEATURE_COLS])[0, 1])

    r = client.get("/api/latest")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["last_updated"] == latest.index[-1].strftime("%Y-%m-%d")
    assert body["spy_price"] == pytest.approx(round(latest["SPY"].iloc[-1], 2))
    assert body["vix_level"] == pytest.approx(round(latest["VIX"].iloc[-1], 2))
    assert body["risk_score_10d"] == pytest.approx(round(expected * 100, 1))
    assert 0 <= body["risk_score_10d"] <= 100
    assert body["market_stress_index"] == pytest.approx(
        round(feature_pipeline.msi["MSI"].loc[latest.index[-1]], 3)
    )
    assert "not a calibrated" in body["risk_score_note"]


def test_latest_risk_rejects_missing_features(client, data_dirs):
    bad = pd.DataFrame(
        {"SPY": [100.0], "VIX": [15.0], "BAA_Treasury_Spread": [2.0]},
        index=pd.Index(pd.to_datetime(["2024-01-02"]), name="Date"),
    )
    bad.to_csv(data_dirs.DATA_FEATURES_DIR / "latest_features.csv")

    r = client.get("/api/latest")
    assert r.status_code == 500
    assert "Missing inference features" in r.json()["detail"]


def test_shap_endpoint_appends_note(client, data_dirs):
    shap_dir = data_dirs.DATA_FEATURES_DIR / "shap"
    shap_dir.mkdir()
    payload = {"date": "2024-01-02", "drivers": [{"feature": "VIX_Level", "shap": 0.4}]}
    (shap_dir / "latest_shap.json").write_text(json.dumps(payload))

    r = client.get("/api/shap")
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == "2024-01-02"
    assert body["drivers"] == payload["drivers"]
    assert "interpretation_note" in body


def test_multi_horizon_endpoint_returns_records(client, data_dirs):
    metrics = pd.DataFrame(
        {"Horizon": ["1D", "1D"], "Model": ["Logistic", "XGBoost"], "ROC_AUC": [0.9, 0.88]}
    )
    metrics.to_csv(data_dirs.DATA_PROCESSED_DIR / "multi_horizon_metrics.csv", index=False)

    r = client.get("/api/multi-horizon-validation")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert body["data"][1]["Model"] == "XGBoost"


def test_validation_endpoint(client, data_dirs):
    df = make_oos_predictions(n=300, start="2020-02-03")
    df.to_csv(data_dirs.DATA_PROCESSED_DIR / "oos_predictions_10d.csv")

    r = client.get("/api/validation")
    assert r.status_code == 200
    body = r.json()

    models = [m["Model"] for m in body["overall_metrics"]]
    assert models == ["Logistic Regression", "XGBoost"]
    assert all(0 <= m["ROC-AUC"] <= 1 for m in body["overall_metrics"])
    assert [e["Event"] for e in body["historical_events"]] == ["2020 COVID-19 Crash"]
