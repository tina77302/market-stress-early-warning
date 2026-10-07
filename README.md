# U.S. Financial Market Stress Early Warning System

> **AI-based early-warning system for broad U.S. financial-market stress using equity, volatility, and credit-market information.**

## Research Question

**Can currently observable financial-market information provide an early warning of a U.S. financial-market Stress Event occurring within the next 10 trading days?**

This is **not a stock-price forecasting or market-timing model**.

The objective is to estimate whether broad U.S. financial-market stress risk is becoming elevated using only information available at each point in time.

---

# 1. System Overview

The system combines information from three major market channels:

- **Equity:** SPY
- **Volatility:** VIX
- **Credit:** Moody's Baa Corporate Yield − 10-Year U.S. Treasury Yield

These inputs are used to construct:

- a **Market Stress Index (MSI)**
- forward Stress Event targets
- **17 predictive features**
- Logistic Regression and XGBoost early-warning models
- walk-forward out-of-sample historical risk scores
- SHAP-based current model explanations
- LOFO out-of-sample signal importance

The fitted XGBoost deployment model produces the latest:

**10-Day Market Stress Risk Score**

The score is an early-warning model output and **is not interpreted as a calibrated event probability**.

---

# 2. Dashboard

The project includes a Next.js dashboard backed by a FastAPI API.

### PAGE 01 — Market Risk Intelligence

Provides:

- current SPY, VIX, and credit-spread conditions
- Market Stress Index
- 10-Day Market Stress Risk Score
- LOW / WATCH / ELEVATED / HIGH risk classification
- market-channel risk summary
- SHAP risk-increasing and risk-reducing drivers
- historical walk-forward OOS Risk Score vs SPY

### PAGE 02 — Model Validation

Provides:

- Logistic Regression vs XGBoost
- 1D / 5D / 10D / 20D horizon validation
- ROC-AUC / PR-AUC / Brier Score
- Precision / Recall / F1
- False Alarm Rate / Missed Event Rate
- historical stress-period analysis
- pre-stress early-warning analysis
- warning-persistence analysis
- LOFO OOS signal importance

### PAGE 03 — Methodology

Documents:

- Stress Event definition
- target construction
- feature specification
- label-overlap purge
- expanding walk-forward validation
- SHAP interpretation
- feature-extension experiments
- model limitations

---

# 3. Market Stress Index

Broad market stress is defined across three dimensions.

| Component | Definition |
|---|---|
| Equity Stress | Negative 21-trading-day SPY return |
| Volatility Stress | VIX level |
| Credit Stress | Baa corporate yield − 10-Year U.S. Treasury yield |

Each component is standardized using a **252-trading-day rolling Z-score**.

The rolling reference distribution is shifted so that the reference statistics for date `t` use only information available before that observation.

The three components receive equal weights:

```text
MSI = (Z_Equity + Z_VIX + Z_Credit) / 3
```

The MSI describes **current market stress**.

It is distinct from the forward-looking Risk Score.

---

# 4. Stress Event and Forward Targets

A Stress Event occurs when the Market Stress Index exceeds a threshold estimated from historical information available at that time.

Forward targets ask whether a Stress Event occurs within a specified future trading horizon.

For the primary 10-day model:

```text
Target_10D(t) = 1
```

if at least one Stress Event occurs during:

```text
t+1 ... t+10
```

Otherwise:

```text
Target_10D(t) = 0
```

Incomplete forward horizons remain unknown rather than being converted into artificial negative observations.

Additional robustness horizons are evaluated at:

- 1 trading day
- 5 trading days
- 10 trading days
- 20 trading days

---

# 5. Final Feature Set — 17 Features

The final specification intentionally remains compact.

## Equity — 7

- SPY 1D Return
- SPY 5D Return
- SPY 20D Return
- SPY 20D Volatility
- SPY 60D Volatility
- SPY Drawdown
- SPY 20D Momentum

## Volatility — 5

- VIX Level
- VIX 1D Change
- VIX 5D Change
- VIX 20D Momentum
- VIX 252D Z-Score

## Credit — 5

- BAA–Treasury Spread Level
- Credit 1D Change
- Credit 5D Change
- Credit 20D Momentum
- Credit 252D Z-Score

Additional variables were retained only when they demonstrated defensible incremental value under the same out-of-sample framework.

---

# 6. Model Selection

Two models are used.

## Logistic Regression

Used as an interpretable linear baseline.

It provides a useful reference for determining whether a more flexible nonlinear model adds practical value.

## XGBoost

Used as the nonlinear deployment model.

It can capture nonlinear relationships and interactions between equity, volatility, and credit-market conditions.

### Why not simply add more algorithms?

The purpose of this project is not to maximize the number of algorithms compared.

Logistic Regression and XGBoost provide two meaningfully different model classes:

```text
Interpretable linear baseline
            ↓
Logistic Regression

Nonlinear tree boosting
            ↓
XGBoost
```

Random Forest would add another tree-based ensemble with a partially overlapping role.

Deep-learning models were not prioritized because the final dataset consists of a relatively small set of structured financial-market features. Increasing model complexity was not assumed to produce more reliable out-of-sample early-warning performance.

Model complexity is therefore kept proportional to the data and research objective.

---

# 7. Leakage-Safe Walk-Forward Validation

Random train/test splitting is **not used**.

Financial time series must preserve chronological order.

Evaluation follows an expanding walk-forward structure:

```text
TRAIN → PURGE → OOS TEST → EXPAND
```

Because an `H`-day target uses future observations through `t+H`, the corresponding validation uses an `H`-observation label-overlap purge.

Therefore:

| Horizon | Purge |
|---:|---:|
| 1D | 1 observation |
| 5D | 5 observations |
| 10D | 10 observations |
| 20D | 20 observations |

This prevents training labels whose forward windows overlap the beginning of the test period.

Historical dashboard Risk Scores are **walk-forward out-of-sample predictions**, not in-sample backfits.

---

# 8. Multi-Horizon OOS Results

## 1-Day Horizon

| Model | ROC-AUC | PR-AUC | Brier | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Logistic | 0.9886 | 0.9247 | 0.0483 | 0.5913 | 0.9556 | 0.7305 |
| XGBoost | 0.9844 | 0.9001 | 0.0398 | 0.6449 | 0.9172 | 0.7573 |

OOS observations: **5,069**

Positive prevalence: **9.77%**

---

## 5-Day Horizon

| Model | ROC-AUC | PR-AUC | Brier | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Logistic | 0.9611 | 0.8557 | 0.0888 | 0.5392 | 0.9113 | 0.6775 |
| XGBoost | 0.9498 | 0.8337 | 0.0710 | 0.6049 | 0.8366 | 0.7021 |

OOS observations: **5,065**

Positive prevalence: **14.02%**

---

## 10-Day Horizon — Primary Model

| Model | ROC-AUC | PR-AUC | Brier | Precision | Recall | F1 | FAR | Missed Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Logistic | 0.9220 | 0.8065 | 0.1282 | 0.4932 | 0.8665 | 0.6286 | 0.1885 | 0.1335 |
| XGBoost | 0.8991 | 0.7778 | 0.0986 | 0.5929 | 0.7760 | 0.6722 | 0.1128 | 0.2240 |

OOS observations: **5,060**

Positive prevalence: **17.47%**

At the fixed `0.5` reference threshold:

- Logistic Regression provides stronger discrimination and recall.
- XGBoost provides higher precision and F1 and fewer false alarms.
- XGBoost also produces the lower Brier score.

XGBoost is therefore **not described as an unconditional performance winner**.

The two models exhibit different operational trade-offs.

---

## 20-Day Horizon

| Model | ROC-AUC | PR-AUC | Brier | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Logistic | 0.8555 | 0.7320 | 0.1752 | 0.4727 | 0.8019 | 0.5948 |
| XGBoost | 0.8138 | 0.7099 | 0.1485 | 0.5495 | 0.6920 | 0.6126 |

OOS observations: **5,050**

Positive prevalence: **22.89%**

Raw model scores should not be compared as literal probabilities across horizons because target prevalence changes mechanically with the forward window.

---

# 9. Early-Warning Analysis

Predictive ranking metrics alone do not answer an operational question:

> **Does the model actually produce warnings before known stress episodes?**

Using 29 historical OOS stress episodes, the proportion containing at least one warning before stress onset was examined.

## Logistic Regression

| Pre-Stress Window | Episodes with ≥1 Warning |
|---|---:|
| 20–11 trading days | 69.0% |
| 10–6 trading days | 72.4% |
| 5–1 trading days | 100.0% |

## XGBoost

| Pre-Stress Window | Episodes with ≥1 Warning |
|---|---:|
| 20–11 trading days | 48.3% |
| 10–6 trading days | 62.1% |
| 5–1 trading days | 86.2% |

These figures are **conditional on known historical stress episodes**.

They are not model accuracy rates.

The 20–11 day window is exploratory because it extends beyond the primary 10-day forecast horizon.

---

# 10. Warning Persistence

A one-day threshold crossing may be transient.

To examine whether persistent warnings are more informative, XGBoost warning episodes are anchored to the **first day the OOS Risk Score crosses the fixed 0.5 reference threshold**.

The analysis then checks whether a Stress Event occurs within the following 20 trading observations.

| Minimum Warning Persistence | Historical Stress Follow-Through |
|---|---:|
| ≥1 day | 38.0% |
| ≥2 days | 48.2% |
| ≥3 days | 57.1% |

Longer warning persistence was historically associated with greater stress follow-through.

This is an experimental warning-episode diagnostic and is distinct from the standard classification False Alarm Rate.

---

# 11. Risk Score ≠ Calibrated Probability

Calibration diagnostics showed overconfidence in several intermediate and high-score regions.

Therefore the dashboard reports:

**Market Stress Risk Score**

rather than:

**Stress Event Probability**

For example:

```text
Risk Score = 70
```

does **not** mean:

```text
70% probability of a Stress Event
```

The score should be interpreted as a model-based relative warning signal.

---

# 12. Risk-Level Communication Bands

For dashboard communication, the 10-day XGBoost Risk Score is grouped into descriptive bands:

| Risk Score | Dashboard Level |
|---:|---|
| < 30 | LOW |
| 30–49.9 | WATCH |
| 50–69.9 | ELEVATED |
| ≥ 70 | HIGH |

These bands are a communication layer rather than calibrated probability intervals.

Historical walk-forward OOS observations showed increasing empirical 10-day Stress Event prevalence as scores increased.

The fixed `0.5` model reference threshold also marks the transition into the ELEVATED range.

---

# 13. SHAP Explainability

SHAP explains the fitted XGBoost deployment model's latest output.

The dashboard separates:

- **Risk Increasing Drivers**
- **Risk Reducing Drivers**

It also aggregates leading SHAP effects into three market channels:

- Stock Market
- Market Volatility
- Credit Conditions

Channel labels represent the **net direction of the leading SHAP contributions**.

Individual variables within the same channel may still move in opposite directions.

SHAP values describe model-output contributions.

They should **not** be interpreted as percentage-point changes in event probability.

---

# 14. SHAP vs LOFO OOS Importance

SHAP and out-of-sample signal importance answer different questions.

### SHAP

> What is driving the fitted model's output?

### LOFO — Leave One Feature Out

> Does this feature provide incremental predictive information out of sample, conditional on the other features?

The primary LOFO metric is:

```text
Δ PR-AUC = Full 17-Feature PR-AUC − Reduced 16-Feature PR-AUC
```

Positive values indicate incremental OOS contribution.

Negative values may indicate redundancy or noise conditional on the remaining features; they do not imply that the underlying financial variable is inherently unimportant.

The strongest consistent unique OOS signals across the two models were:

- **VIX 252D Z-Score**
- **Credit Spread 252D Z-Score**

This suggests that the **relative level of volatility and credit stress compared with their own recent history** contains particularly useful early-warning information.

LOFO is used for interpretation, not automatic feature pruning.

The final specification remains the predefined 17-feature set.

---

# 15. Feature Extensions and Ablation Tests

Additional market variables were evaluated under the same purged walk-forward OOS framework.

Variables were not retained simply because they were economically plausible.

They had to demonstrate consistent incremental predictive value.

## U.S. Rates / Yield Curve

Treasury-rate and yield-curve variables were evaluated as an extension of the core model.

They did not provide consistent incremental OOS predictive value over the existing equity, volatility, and credit features.

**Decision: excluded from final specification.**

This does not imply that interest rates are economically unimportant.

---

## Banking / Liquidity

Banking and liquidity indicators were evaluated after the 2023 U.S. banking turmoil.

Under the same purged walk-forward OOS framework, they did not provide consistent incremental predictive value over the core 17-feature model.

**Decision: excluded.**

The 2023 banking turmoil temporarily elevated model Risk Scores but did not satisfy the project's broad-market Stress Event definition.

The target was not redefined post hoc to force the episode to become a positive event.

---

## Market Breadth — RSP / SPY

An equity-breadth extension using RSP relative to SPY was evaluated.

### Logistic Regression

```text
Core 17F PR-AUC:    0.7477
Breadth 20F PR-AUC: 0.7242
```

### XGBoost

```text
Core 17F PR-AUC:    0.7425
Breadth 20F PR-AUC: 0.7273
```

The breadth extension did not improve OOS performance.

**Decision: excluded.**

---

## Bitcoin

Bitcoin-related features were evaluated on a common post-2014 sample to avoid giving the extended model a different evaluation period.

### Logistic Regression

```text
Core 17F PR-AUC: 0.7150
BTC 21F PR-AUC:  0.7004
```

### XGBoost

```text
Core 17F PR-AUC: 0.7472
BTC 21F PR-AUC:  0.7389
```

Bitcoin reacted to several stress periods, but its addition did not materially improve early-warning performance in this framework.

**Decision: excluded.**

---

# 16. Credit-Spread Proxy

The credit variable is:

**Moody's Seasoned Baa Corporate Bond Yield − 10-Year U.S. Treasury Constant Maturity Rate**

It is a **Baa–Treasury credit-stress proxy**.

It should not be described as ICE BofA High Yield OAS.

A long-history credit proxy was used so that validation could include major historical stress periods such as the Global Financial Crisis.

---

# 17. API

| Endpoint | Purpose |
|---|---|
| `GET /health` | API health |
| `GET /api/latest` | Latest market data, MSI and Risk Score |
| `GET /api/shap` | Latest XGBoost SHAP drivers |
| `GET /api/historical` | Historical walk-forward OOS series |
| `GET /api/validation` | Primary OOS validation |
| `GET /api/multi-horizon-validation` | 1D / 5D / 10D / 20D validation |

---

# 18. Tech Stack

### Machine Learning / Data

- Python
- pandas
- NumPy
- scikit-learn
- XGBoost
- SHAP

### Backend

- FastAPI
- Uvicorn

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- Recharts

### Market Data

- Yahoo Finance
- FRED

---

# 19. Local Development

## Backend

```bash
cd market-stress-early-warning

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

python run_pipeline.py
python -m src.explainability.shap_analysis

uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

API:

```text
http://localhost:8000
```

Health check:

```text
http://localhost:8000/health
```

## Frontend

Open a separate terminal:

```bash
cd market-stress-early-warning/frontend

npm install
npm run dev
```

Dashboard:

```text
http://localhost:3000
```

---

# 20. Limitations

- The Risk Score is not a calibrated event probability.
- The target represents **broad U.S. financial-market stress**, not every type of financial incident.
- Credit stress is represented using a long-history Baa–Treasury proxy rather than ICE BofA HY OAS.
- Historical performance is based on purged walk-forward OOS predictions.
- Current SHAP explains the fitted deployment model rather than historical OOS models.
- Warning-persistence analysis is an experimental diagnostic and should not be confused with standard classification FAR.
- Feature-extension results depend on the specific variable definitions, data availability, sample period, and validation framework used here.
- Historical crisis performance does not guarantee detection of future crises.
- The system is not an individual-stock trading signal or direct market-timing strategy.

---

# 21. Research Principle

> **Methodological defensibility takes priority over model complexity or feature count.**

The project deliberately distinguishes:

```text
Current stress       → Market Stress Index
Forward warning      → Market Stress Risk Score
Model explanation    → SHAP
Incremental OOS info → LOFO
```

Additional variables are retained only when they demonstrate defensible incremental value under the same leakage-safe out-of-sample framework.

---

# Korean Summary | 한국어 요약

이 프로젝트는 **미국 금융시장 스트레스 조기경보 시스템**입니다.

단순히 SPY의 상승·하락을 예측하는 주가예측 모델이 아니라,

> **현재 관측 가능한 주식시장·변동성·신용시장 정보를 이용해 향후 미국 금융시장의 광범위한 Stress Event 위험 상승을 조기에 탐지할 수 있는가?**

를 검증하는 것이 핵심 목적입니다.

### 핵심 구조

```text
SPY + VIX + Credit Spread
          ↓
Market Stress Index
          ↓
17개 금융시장 Feature
          ↓
Logistic Regression + XGBoost
          ↓
Purged Walk-Forward OOS Validation
          ↓
10-Day Market Stress Risk Score
```

시계열 누수를 방지하기 위해 random train/test split 대신 **expanding walk-forward validation**을 사용하며, forward target의 기간에 맞는 **label-overlap purge**를 적용합니다.

Logistic Regression은 해석 가능한 baseline, XGBoost는 비선형 관계를 포착하는 deployment model로 사용합니다.

10D OOS 결과에서 Logistic Regression은 ROC-AUC와 Recall 측면에서 강점을 보였고, XGBoost는 Precision, F1, False Alarm Rate 및 Brier Score 측면에서 강점을 보였습니다.

따라서 XGBoost를 단순히 “가장 성능이 좋은 모델”이라고 주장하지 않습니다.

또한 모델의 raw output에서 calibration 문제가 확인되었기 때문에 웹사이트에서는 이를 실제 발생확률이 아니라 **Market Stress Risk Score**라고 표현합니다.

SHAP은 현재 모델 출력의 주요 원인을 설명하고, LOFO 분석은 각 feature가 다른 변수들을 통제한 상태에서 실제 OOS 예측력에 추가 정보를 제공하는지를 검증합니다.

금리/수익률곡선, Banking/Liquidity, Market Breadth, Bitcoin 관련 변수도 추가 검증했지만 동일한 OOS 환경에서 일관된 증분 예측력을 확인하지 못해 최종 17개 feature에서는 제외했습니다.

이 프로젝트의 핵심 원칙은:

> **변수나 모델의 개수를 늘리는 것보다 실제 Out-of-Sample 환경에서 검증 가능한 방법론적 타당성을 우선하는 것**

입니다.