U.S. Financial Market Stress Early Warning System
AI-based early-warning system for U.S. financial-market stress using equity, volatility, and credit-market information.
Research question: Can currently observable financial-market information provide an early warning of a U.S. financial-market Stress Event occurring within the next 10 trading days?

This is not a stock-price forecasting model. The objective is to identify elevated broad-market stress risk using information available at each point in time.
System Overview
The system combines SPY (equity), VIX (volatility), and a Moody's Baa corporate yield − 10-Year U.S. Treasury yield credit-spread proxy. These inputs form the Market Stress Index (MSI), forward 10-day target, and 17 predictive features.
The fitted XGBoost deployment model produces the latest 10-Day Market Stress Risk Score, while SHAP identifies current risk-increasing and risk-reducing drivers.
Dashboard
PAGE 01 — Market Risk: current market indicators, MSI, 10-Day Risk Score, SHAP drivers, and historical OOS risk vs SPY.
PAGE 02 — Model Validation: Logistic vs XGBoost OOS performance, evaluation metrics, and historical stress-period analysis.
PAGE 03 — Methodology: stress/target definitions, feature specification, purged walk-forward validation, SHAP, rate-feature ablation, and limitations.
Market Stress Index
Component	Definition
Equity Stress	Negative 21-trading-day SPY return
Volatility Stress	VIX level
Credit Stress	Baa corporate yield − 10-Year U.S. Treasury yield


Each component is standardized with a 252-trading-day rolling Z-score shifted by one observation, so the reference distribution for date t uses only prior information. The three components receive equal weights.
MSI = (Z_Equity + Z_VIX + Z_Credit) / 3
Forward 10-Day Target
Target_10D(t) = 1 if at least one defined Stress Event occurs during trading days t+1 through t+10; otherwise it equals 0.
Incomplete forward horizons remain unknown rather than being converted into artificial negatives. Stress thresholds are estimated using past information only.
Final Feature Set — 17 Features
Equity (7): SPY 1D Return, 5D Return, 20D Return, 20D Volatility, 60D Volatility, Drawdown, 20D Momentum.
Volatility (5): VIX Level, 1D Change, 5D Change, 20D Momentum, 252D Z-Score.
Credit (5): BAA–Treasury Spread Level, Credit 1D Change, 5D Change, 20D Momentum, 252D Z-Score.
Models and Purged Walk-Forward Validation
Logistic Regression is the interpretable baseline. XGBoost captures nonlinear relationships and interactions and is the current deployment model.
Random train/test splitting is not used. Evaluation follows:
TRAIN → 10D PURGE → OOS TEST → EXPAND
The 10-trading-observation label-overlap purge prevents training labels whose forward target windows overlap the beginning of the test period. Historical dashboard predictions are walk-forward out-of-sample predictions, not in-sample backfits.
Walk-Forward OOS Results
- OOS period: 2006-08-09 → 2026-09-16
- Observations: 5,057
- Positive prevalence: 17.48%
Model	ROC-AUC	PR-AUC	Brier	Precision	Recall	F1
Logistic Regression	0.9219	0.8066	0.1283	0.4932	0.8665	0.6286
XGBoost	0.8991	0.7785	0.0984	0.5939	0.7760	0.6729


At the fixed 0.5 reference threshold, Logistic FAR/Missed Event Rate = 0.1886 / 0.1335; XGBoost = 0.1124 / 0.2240.
Logistic provides stronger OOS discrimination and recall. XGBoost provides fewer false alarms and stronger precision/F1 at the fixed reference threshold, plus a lower Brier score. XGBoost is therefore not described as an unconditional winner.
Risk Score ≠ Calibrated Probability
Calibration diagnostics showed overconfidence in several intermediate/high-score regions. The dashboard therefore reports a 10-Day Market Stress Risk Score, not a literal event probability. A score of 70 should not be interpreted as exactly 70% event probability.
SHAP Explainability
SHAP explains the fitted XGBoost deployment model's latest score. The dashboard separates Risk Increasing Drivers and Risk Reducing Drivers.
SHAP values indicate direction and relative model-output contribution; they are not probability-point changes.
Endpoint: GET /api/shap
Credit-Spread Proxy
The credit variable is Moody's Seasoned Baa Corporate Bond Yield minus the 10-Year U.S. Treasury Constant Maturity Rate. It is a Baa–Treasury credit-stress proxy, not ICE BofA High Yield OAS. Its long history supports validation through periods including 2008.
Rate-Feature Ablation
Four U.S. Treasury/yield-curve features were tested under the same purged walk-forward OOS framework, temporarily expanding 17 features to 21.
Metric	17F	21F
Logistic ROC-AUC	0.9219	0.9158
Logistic PR-AUC	0.8066	0.7855
XGBoost ROC-AUC	0.8991	0.9010
XGBoost PR-AUC	0.7785	0.7731


The rate features did not demonstrate consistent incremental OOS predictive value, so the final specification remains 17 features. This does not imply rates are economically unimportant.
API
Endpoint	Purpose
GET /health	API health
GET /api/latest	Latest market data, MSI and Risk Score
GET /api/shap	Latest XGBoost SHAP drivers
GET /api/historical	Historical walk-forward OOS series
GET /api/validation	OOS validation results


Tech Stack
ML/Data: Python, pandas, scikit-learn, XGBoost, SHAP
Backend: FastAPI, Uvicorn
Frontend: Next.js, React, TypeScript, Tailwind CSS, Recharts
Market Data: Yahoo Finance, FRED
Local Development
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py
python -m src.explainability.shap_analysis
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
Frontend:
cd frontend
npm install
npm run dev
Limitations
- Risk Score is not a calibrated event probability.
- Credit is represented by a long-history Baa–Treasury proxy rather than ICE BofA HY OAS.
- Historical performance uses purged walk-forward OOS predictions; current SHAP explains the fitted deployment model.
- The system estimates broad U.S. financial-market stress risk, not a stock trading signal or direct market-timing strategy.
- Historical performance does not guarantee future crisis detection.
Research Principle
Methodological defensibility takes priority over adding variables that do not demonstrate incremental out-of-sample value.

한국어 설명 | Korean Guide
프로젝트 소개
이 프로젝트는 미국 금융시장 스트레스 조기경보 시스템입니다.
단순히 “향후 SPY가 하락할 것인가?”를 예측하는 주가예측 모델이 아니라, 현재 시점에서 관측 가능한 주식시장·변동성·신용시장 정보를 이용해 향후 10거래일 이내 미국 금융시장 Stress Event 발생 위험이 높아지는지를 조기에 탐지하는 것을 목표로 합니다.
핵심 연구 질문은 다음과 같습니다.
현재 이용 가능한 금융시장 정보를 활용하여 향후 10거래일 이내 미국 금융시장 Stress Event 발생 가능성을 조기에 예측할 수 있는가?

핵심 데이터
시스템은 서로 다른 세 가지 금융시장 정보를 결합합니다.
- SPY: 미국 주식시장 상황
- VIX: 시장의 기대 변동성
- BAA–Treasury Spread: Moody's Baa 회사채 금리 − 미국 10년물 국채금리로 계산한 신용 스트레스 대용치
이 세 시장 정보를 기반으로 Market Stress Index(MSI)를 만들고, 17개 머신러닝 피처를 생성하여 Logistic Regression과 XGBoost를 비교합니다.
Market Stress Index
시장 스트레스는 단순한 주가 하락이 아니라 세 가지 차원으로 정의합니다.
구성요소	정의
Equity Stress	SPY 21거래일 수익률의 음수값
Volatility Stress	VIX 수준
Credit Stress	Baa 회사채 금리 − 미국 10년물 국채금리


각 변수는 252거래일 rolling Z-score로 표준화합니다. 이때 shift(1)을 적용해 날짜 t의 기준 평균과 표준편차 계산에는 t-1까지의 정보만 사용합니다.
세 요소에는 임의적인 중요도 차이를 두지 않고 동일 가중치를 적용합니다.
MSI = (Z_Equity + Z_VIX + Z_Credit) / 3
10거래일 Forward Target
날짜 t를 기준으로 향후 t+1부터 t+10 거래일 사이에 Stress Event가 한 번이라도 발생하면:
Target_10D(t) = 1
그렇지 않으면 0입니다.
향후 10거래일이 완전히 존재하지 않는 최근 관측치는 억지로 0으로 처리하지 않고 unknown으로 남깁니다. Stress Event 기준 역시 해당 시점까지 이용 가능한 과거 정보만으로 산출합니다.
최종 17개 피처
주식시장 7개
- SPY 1D Return
- SPY 5D Return
- SPY 20D Return
- SPY 20D Volatility
- SPY 60D Volatility
- SPY Drawdown
- SPY 20D Momentum
변동성 5개
- VIX Level
- VIX 1D Change
- VIX 5D Change
- VIX 20D Momentum
- VIX 252D Z-Score
신용시장 5개
- BAA–Treasury Spread Level
- Credit 1D Change
- Credit 5D Change
- Credit 20D Momentum
- Credit 252D Z-Score
모델과 검증 방식
Logistic Regression은 해석 가능한 baseline 모델로 사용합니다.
XGBoost는 변수 간 비선형 관계와 interaction을 포착하기 위한 모델이며 현재 웹서비스의 deployment model로 사용합니다.
시계열 데이터에서 미래 정보가 과거 학습에 섞이는 문제를 방지하기 위해 random train/test split을 사용하지 않고 expanding-window walk-forward validation을 적용합니다.
TRAIN → 10D PURGE → OOS TEST → EXPAND
Target 자체가 향후 10거래일을 참조하기 때문에 테스트 구간 직전에는 10거래일 label-overlap purge를 둡니다. 이를 통해 학습 데이터의 target window가 테스트 구간과 겹치는 것을 방지합니다.
웹사이트의 과거 위험 점수 역시 in-sample 재현값이 아니라 walk-forward OOS prediction을 사용합니다.
최종 OOS 성능
- 검증 기간: 2006-08-09 ~ 2026-09-16
- OOS 관측치: 5,057개
- Positive prevalence: 17.48%
모델	ROC-AUC	PR-AUC	Brier	Precision	Recall	F1
Logistic Regression	0.9219	0.8066	0.1283	0.4932	0.8665	0.6286
XGBoost	0.8991	0.7785	0.0984	0.5939	0.7760	0.6729


고정된 0.5 기준에서 Logistic Regression은 높은 Recall과 낮은 Missed Event Rate를 보였고, XGBoost는 낮은 False Alarm Rate와 높은 Precision/F1을 보였습니다.
따라서 XGBoost를 단순히 “성능이 가장 좋은 모델”이라고 주장하지 않습니다. 두 모델은 서로 다른 성능상의 장점을 보이며, XGBoost는 현재 deployment model로 사용합니다.
Risk Score를 확률이라고 부르지 않는 이유
Calibration 분석 결과 raw model output은 특히 중간~높은 점수 영역에서 실제 발생률보다 과신하는 경향이 확인되었습니다.
따라서 웹사이트에서는 이를 10-Day Market Stress Risk Score라고 표현합니다.
예를 들어 Risk Score가 70이라고 해서 “Stress Event가 발생할 확률이 정확히 70%”라는 의미는 아닙니다. 점수가 높을수록 모델이 판단한 상대적인 시장 스트레스 위험이 높다는 의미입니다.
SHAP Explainability
최신 XGBoost 위험 점수가 왜 만들어졌는지 설명하기 위해 SHAP을 적용했습니다.
웹사이트에서는 주요 요인을 다음 두 그룹으로 나눕니다.
- Risk Increasing Drivers: 현재 위험 점수를 높이는 변수
- Risk Reducing Drivers: 현재 위험 점수를 낮추는 변수
SHAP 값은 모델 출력에 대한 변수의 방향과 상대적 기여도를 의미하며, 발생확률의 퍼센트포인트 변화량을 의미하지 않습니다.
금리 변수 Ablation Test
미국 2년물·10년물 국채금리와 10Y–2Y 수익률곡선 관련 변수를 추가하여 기존 17개 피처를 21개로 확장한 실험도 수행했습니다.
동일한 purged walk-forward OOS 환경에서 비교한 결과:
지표	17F	21F
Logistic ROC-AUC	0.9219	0.9158
Logistic PR-AUC	0.8066	0.7855
XGBoost ROC-AUC	0.8991	0.9010
XGBoost PR-AUC	0.7785	0.7731


일부 지표에서는 소폭 개선이 있었지만 전체적으로 일관된 증분 OOS 예측력을 확인하지 못했습니다. 따라서 최종 모델에서는 기존 17개 피처를 유지했습니다.
이는 금리가 금융시장에서 중요하지 않다는 뜻이 아니라, 이번 모델과 변수 정의에서는 기존 주식·변동성·신용 정보에 추가되는 안정적인 예측력을 확인하지 못했다는 의미입니다.
주요 API
Endpoint	기능
GET /health	API 상태 확인
GET /api/latest	최신 시장정보, MSI, Risk Score
GET /api/shap	최신 XGBoost SHAP 설명
GET /api/historical	과거 walk-forward OOS 데이터
GET /api/validation	모델 OOS 성능 및 검증 결과


해석 시 주의사항
- Risk Score는 calibration이 완료된 실제 발생확률이 아닙니다.
- Credit 변수는 ICE BofA HY OAS가 아니라 장기 시계열 확보를 위한 Baa–Treasury spread proxy입니다.
- 과거 성능 분석은 purged walk-forward OOS prediction을 사용하지만, 최신 SHAP은 전체 관측 가능한 labeled data로 학습된 deployment model을 설명합니다.
- 이 시스템은 미국 금융시장의 광범위한 스트레스 위험을 탐지하기 위한 것으로, 개별 종목 매매신호나 직접적인 market-timing 전략이 아닙니다.
- 과거 위기에서의 성능이 미래 위기 탐지를 보장하지 않습니다.
프로젝트 원칙
변수를 많이 추가하는 것보다, 실제 Out-of-Sample 환경에서 검증 가능한 방법론적 타당성을 우선한다