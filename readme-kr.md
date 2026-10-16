# 미국 금융시장 스트레스 조기경보 시스템

> **주식·변동성·신용시장 정보를 활용한 미국 금융시장 전반의 스트레스에 대한 AI 기반 조기경보 시스템**

> 이 문서는 [README.md](README.md)의 한국어 번역본입니다.

## 연구 질문

**현재 관측 가능한 금융시장 정보가 향후 10거래일 이내에 발생하는 미국 금융시장 Stress Event를 조기에 경고할 수 있는가?**

이 프로젝트는 **주가 예측 모델이나 마켓 타이밍 모델이 아닙니다.**

목표는 각 시점에서 이용 가능한 정보만을 사용하여 미국 금융시장 전반의 스트레스 위험이 상승하고 있는지를 추정하는 것입니다.

---

# 1. 시스템 개요

이 시스템은 세 가지 주요 시장 채널의 정보를 결합합니다.

- **주식(Equity):** SPY
- **변동성(Volatility):** VIX
- **신용(Credit):** Moody's Baa 회사채 수익률 − 미국 10년 국채 수익률

이 입력값으로 다음을 구성합니다.

- **Market Stress Index (MSI)**
- 미래(forward) Stress Event 타깃
- **17개의 예측 Feature**
- Logistic Regression 및 XGBoost 조기경보 모델
- Walk-forward 방식의 Out-of-Sample(OOS) 과거 리스크 스코어
- SHAP 기반 현재 모델 설명
- LOFO 기반 OOS 신호 중요도

학습된 XGBoost 배포 모델은 최신의 다음 값을 산출합니다.

**10-Day Market Stress Risk Score**

이 스코어는 조기경보 모델의 출력값이며 **보정된(calibrated) 사건 발생 확률로 해석하지 않습니다.**

---

# 2. 대시보드

이 프로젝트는 FastAPI API를 백엔드로 하는 Next.js 대시보드를 포함합니다.

### PAGE 01 — Market Risk Intelligence

제공 내용:

- 현재 SPY, VIX, 신용 스프레드 상황
- Market Stress Index
- 10-Day Market Stress Risk Score
- LOW / WATCH / ELEVATED / HIGH 리스크 분류
- 시장 채널별 리스크 요약
- SHAP 기반 리스크 상승 요인 및 리스크 하락 요인
- 과거 Walk-forward OOS Risk Score와 SPY 비교

### PAGE 02 — Model Validation

제공 내용:

- Logistic Regression vs XGBoost
- 1D / 5D / 10D / 20D 예측 기간(horizon) 검증
- ROC-AUC / PR-AUC / Brier Score
- Precision / Recall / F1
- False Alarm Rate / Missed Event Rate
- 과거 스트레스 기간 분석
- 스트레스 발생 전 조기경보 분석
- 경보 지속성(warning-persistence) 분석
- LOFO OOS 신호 중요도

### PAGE 03 — Methodology

문서화 내용:

- Stress Event 정의
- 타깃 구성 방식
- Feature 명세
- Label-overlap purge
- Expanding walk-forward 검증
- SHAP 해석
- Feature 확장 실험
- 모델 한계

---

# 3. Market Stress Index

시장 전반의 스트레스는 세 가지 차원으로 정의됩니다.

| 구성 요소 | 정의 |
|---|---|
| Equity Stress | 21거래일 SPY 수익률의 음수값 |
| Volatility Stress | VIX 수준 |
| Credit Stress | Baa 회사채 수익률 − 미국 10년 국채 수익률 |

각 구성 요소는 **252거래일 롤링 Z-score**로 표준화됩니다.

롤링 참조 분포는 시점 `t`의 참조 통계량이 해당 관측치 이전의 정보만 사용하도록 한 시점 뒤로 이동(shift)됩니다.

세 구성 요소는 동일한 가중치를 가집니다.

```text
MSI = (Z_Equity + Z_VIX + Z_Credit) / 3
```

MSI는 **현재의 시장 스트레스**를 나타냅니다.

미래를 바라보는 Risk Score와는 구별되는 지표입니다.

---

# 4. Stress Event와 Forward 타깃

Stress Event는 Market Stress Index가 해당 시점까지 이용 가능한 과거 정보로 추정한 임계값을 초과할 때 발생합니다.

Forward 타깃은 지정된 미래 거래일 기간 내에 Stress Event가 발생하는지를 묻습니다.

주 모델인 10일 모델의 경우:

```text
Target_10D(t) = 1
```

다음 기간 동안 Stress Event가 한 번 이상 발생하면:

```text
t+1 ... t+10
```

그렇지 않으면:

```text
Target_10D(t) = 0
```

미래 기간이 완전히 관측되지 않은 경우에는 인위적인 음성(negative) 관측치로 변환하지 않고 미지(unknown) 상태로 유지합니다.

추가적인 강건성 검증을 위해 다음 기간도 평가합니다.

- 1거래일
- 5거래일
- 10거래일
- 20거래일

---

# 5. 최종 Feature 세트 — 17개

최종 명세는 의도적으로 간결하게 유지됩니다.

## 주식(Equity) — 7개

- SPY 1D Return
- SPY 5D Return
- SPY 20D Return
- SPY 20D Volatility
- SPY 60D Volatility
- SPY Drawdown
- SPY 20D Momentum

## 변동성(Volatility) — 5개

- VIX Level
- VIX 1D Change
- VIX 5D Change
- VIX 20D Momentum
- VIX 252D Z-Score

## 신용(Credit) — 5개

- BAA–Treasury Spread Level
- Credit 1D Change
- Credit 5D Change
- Credit 20D Momentum
- Credit 252D Z-Score

추가 변수는 동일한 Out-of-Sample 프레임워크에서 방어 가능한 증분 가치를 입증한 경우에만 유지되었습니다.

---

# 6. 모델 선택

두 가지 모델을 사용합니다.

## Logistic Regression

해석 가능한 선형 베이스라인으로 사용합니다.

보다 유연한 비선형 모델이 실질적인 가치를 더하는지 판단하는 데 유용한 기준점을 제공합니다.

## XGBoost

비선형 배포 모델로 사용합니다.

주식·변동성·신용시장 상황 간의 비선형 관계와 상호작용을 포착할 수 있습니다.

### 왜 알고리즘을 더 추가하지 않는가?

이 프로젝트의 목적은 비교하는 알고리즘의 수를 극대화하는 것이 아닙니다.

Logistic Regression과 XGBoost는 의미 있게 서로 다른 두 가지 모델 클래스를 제공합니다.

```text
해석 가능한 선형 베이스라인
            ↓
Logistic Regression

비선형 트리 부스팅
            ↓
XGBoost
```

Random Forest는 역할이 부분적으로 겹치는 또 하나의 트리 기반 앙상블을 추가하는 것에 그칩니다.

딥러닝 모델은 우선순위에서 제외되었습니다. 최종 데이터셋이 비교적 적은 수의 구조화된 금융시장 Feature로 구성되어 있기 때문입니다. 모델 복잡도를 높이는 것이 더 신뢰할 수 있는 Out-of-Sample 조기경보 성능을 만든다고 가정하지 않았습니다.

따라서 모델 복잡도는 데이터와 연구 목적에 비례하는 수준으로 유지됩니다.

---

# 7. 누수 방지(Leakage-Safe) Walk-Forward 검증

무작위 train/test 분할은 **사용하지 않습니다.**

금융 시계열은 시간 순서를 보존해야 합니다.

평가는 expanding walk-forward 구조를 따릅니다.

```text
TRAIN → PURGE → OOS TEST → EXPAND
```

`H`일 타깃은 `t+H`까지의 미래 관측치를 사용하므로, 해당 검증에서는 `H`개 관측치의 label-overlap purge를 적용합니다.

따라서:

| 예측 기간 | Purge |
|---:|---:|
| 1D | 1 관측치 |
| 5D | 5 관측치 |
| 10D | 10 관측치 |
| 20D | 20 관측치 |

이를 통해 forward 윈도우가 테스트 기간의 시작 부분과 겹치는 학습 레이블을 방지합니다.

대시보드의 과거 Risk Score는 **Walk-forward Out-of-Sample 예측값**이며, In-sample 백핏(backfit)이 아닙니다.

---

# 8. 다중 예측 기간 OOS 결과

## 1일 예측 기간

| 모델 | ROC-AUC | PR-AUC | Brier | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Logistic | 0.9886 | 0.9247 | 0.0483 | 0.5913 | 0.9556 | 0.7305 |
| XGBoost | 0.9844 | 0.9001 | 0.0398 | 0.6449 | 0.9172 | 0.7573 |

OOS 관측치 수: **5,069**

양성 비율: **9.77%**

---

## 5일 예측 기간

| 모델 | ROC-AUC | PR-AUC | Brier | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Logistic | 0.9611 | 0.8557 | 0.0888 | 0.5392 | 0.9113 | 0.6775 |
| XGBoost | 0.9498 | 0.8337 | 0.0710 | 0.6049 | 0.8366 | 0.7021 |

OOS 관측치 수: **5,065**

양성 비율: **14.02%**

---

## 10일 예측 기간 — 주 모델

| 모델 | ROC-AUC | PR-AUC | Brier | Precision | Recall | F1 | FAR | Missed Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Logistic | 0.9220 | 0.8065 | 0.1282 | 0.4932 | 0.8665 | 0.6286 | 0.1885 | 0.1335 |
| XGBoost | 0.8991 | 0.7778 | 0.0986 | 0.5929 | 0.7760 | 0.6722 | 0.1128 | 0.2240 |

OOS 관측치 수: **5,060**

양성 비율: **17.47%**

고정 기준 임계값 `0.5`에서:

- Logistic Regression은 더 강한 판별력(discrimination)과 Recall을 보입니다.
- XGBoost는 더 높은 Precision과 F1, 더 적은 오경보(false alarm)를 보입니다.
- XGBoost는 더 낮은 Brier Score도 기록합니다.

따라서 XGBoost를 **무조건적인 성능 우위 모델로 설명하지 않습니다.**

두 모델은 서로 다른 운영상의 트레이드오프를 보입니다.

---

## 20일 예측 기간

| 모델 | ROC-AUC | PR-AUC | Brier | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Logistic | 0.8555 | 0.7320 | 0.1752 | 0.4727 | 0.8019 | 0.5948 |
| XGBoost | 0.8138 | 0.7099 | 0.1485 | 0.5495 | 0.6920 | 0.6126 |

OOS 관측치 수: **5,050**

양성 비율: **22.89%**

타깃의 양성 비율은 forward 윈도우에 따라 기계적으로 변하므로, 모델의 원시(raw) 스코어를 예측 기간 간에 문자 그대로의 확률로 비교해서는 안 됩니다.

---

# 9. 조기경보 분석

예측 순위(ranking) 지표만으로는 다음과 같은 운영상의 질문에 답할 수 없습니다.

> **모델이 알려진 스트레스 에피소드 이전에 실제로 경보를 발생시키는가?**

29개의 과거 OOS 스트레스 에피소드를 대상으로, 스트레스 시작 이전에 최소 한 번의 경보가 포함된 에피소드의 비율을 조사했습니다.

## Logistic Regression

| 스트레스 발생 전 윈도우 | 경보 1회 이상 발생 에피소드 비율 |
|---|---:|
| 20–11거래일 전 | 69.0% |
| 10–6거래일 전 | 72.4% |
| 5–1거래일 전 | 100.0% |

## XGBoost

| 스트레스 발생 전 윈도우 | 경보 1회 이상 발생 에피소드 비율 |
|---|---:|
| 20–11거래일 전 | 48.3% |
| 10–6거래일 전 | 62.1% |
| 5–1거래일 전 | 86.2% |

이 수치는 **알려진 과거 스트레스 에피소드를 조건으로 한 값**입니다.

모델의 정확도(accuracy)가 아닙니다.

20–11일 윈도우는 주 예측 기간인 10일을 넘어서므로 탐색적(exploratory) 분석입니다.

---

# 10. 경보 지속성(Warning Persistence)

하루 동안의 임계값 돌파는 일시적일 수 있습니다.

지속적인 경보가 더 많은 정보를 담고 있는지 확인하기 위해, XGBoost 경보 에피소드를 **OOS Risk Score가 고정 기준 임계값 0.5를 처음 넘은 날**을 기준점으로 삼습니다.

그 후 이어지는 20개 거래일 관측치 내에 Stress Event가 발생하는지를 확인합니다.

| 최소 경보 지속 기간 | 과거 스트레스 실제 발생 비율 |
|---|---:|
| 1일 이상 | 38.0% |
| 2일 이상 | 48.2% |
| 3일 이상 | 57.1% |

경보가 오래 지속될수록 과거에 스트레스로 이어진 비율이 높았습니다.

이는 실험적인 경보 에피소드 진단 지표이며, 표준 분류 지표인 False Alarm Rate와는 구별됩니다.

---

# 11. Risk Score ≠ 보정된 확률

보정(calibration) 진단에서 여러 중간 및 고점수 구간에서 과신(overconfidence)이 확인되었습니다.

따라서 대시보드에서는 다음과 같이 표기합니다.

**Market Stress Risk Score**

다음과 같이 표기하지 않습니다.

**Stress Event Probability**

예를 들어:

```text
Risk Score = 70
```

은 다음을 의미하지 **않습니다.**

```text
Stress Event 발생 확률 70%
```

이 스코어는 모델 기반의 상대적 경보 신호로 해석해야 합니다.

---

# 12. 리스크 수준 커뮤니케이션 구간

대시보드 커뮤니케이션을 위해 10일 XGBoost Risk Score를 서술적인 구간으로 그룹화합니다.

| Risk Score | 대시보드 수준 |
|---:|---|
| < 30 | LOW |
| 30–49.9 | WATCH |
| 50–69.9 | ELEVATED |
| ≥ 70 | HIGH |

이 구간은 보정된 확률 구간이 아니라 커뮤니케이션 계층입니다.

과거 Walk-forward OOS 관측치에서는 스코어가 높아질수록 10일 Stress Event의 경험적 발생 비율이 증가하는 것으로 나타났습니다.

고정 모델 기준 임계값 `0.5`는 ELEVATED 구간으로의 전환점이기도 합니다.

---

# 13. SHAP 설명 가능성

SHAP은 학습된 XGBoost 배포 모델의 최신 출력값을 설명합니다.

대시보드는 다음을 구분합니다.

- **리스크 상승 요인(Risk Increasing Drivers)**
- **리스크 하락 요인(Risk Reducing Drivers)**

또한 주요 SHAP 효과를 세 가지 시장 채널로 집계합니다.

- 주식시장(Stock Market)
- 시장 변동성(Market Volatility)
- 신용 상황(Credit Conditions)

채널 라벨은 **주요 SHAP 기여도의 순방향(net direction)**을 나타냅니다.

같은 채널 내의 개별 변수는 여전히 서로 반대 방향으로 움직일 수 있습니다.

SHAP 값은 모델 출력에 대한 기여도를 설명합니다.

사건 발생 확률의 퍼센트 포인트 변화로 해석해서는 **안 됩니다.**

---

# 14. SHAP vs LOFO OOS 중요도

SHAP과 Out-of-Sample 신호 중요도는 서로 다른 질문에 답합니다.

### SHAP

> 학습된 모델의 출력을 무엇이 움직이고 있는가?

### LOFO — Leave One Feature Out

> 다른 Feature를 조건으로 할 때, 이 Feature가 Out-of-Sample에서 증분 예측 정보를 제공하는가?

주요 LOFO 지표는 다음과 같습니다.

```text
Δ PR-AUC = 전체 17-Feature PR-AUC − 축소 16-Feature PR-AUC
```

양수 값은 OOS 증분 기여를 나타냅니다.

음수 값은 나머지 Feature를 조건으로 할 때 중복성 또는 노이즈를 나타낼 수 있습니다. 이는 해당 금융 변수가 본질적으로 중요하지 않다는 의미는 아닙니다.

두 모델에서 가장 일관되게 나타난 고유한 OOS 신호는 다음과 같습니다.

- **VIX 252D Z-Score**
- **Credit Spread 252D Z-Score**

이는 **변동성과 신용 스트레스가 자신의 최근 이력에 비해 상대적으로 어느 수준에 있는지**가 특히 유용한 조기경보 정보를 담고 있음을 시사합니다.

LOFO는 해석을 위해 사용되며, 자동 Feature 제거(pruning)에는 사용되지 않습니다.

최종 명세는 사전에 정의된 17개 Feature 세트로 유지됩니다.

---

# 15. Feature 확장 및 제거(Ablation) 실험

동일한 purged walk-forward OOS 프레임워크에서 추가 시장 변수를 평가했습니다.

경제적으로 타당하다는 이유만으로 변수를 유지하지는 않았습니다.

일관된 증분 예측 가치를 입증해야 했습니다.

## 미국 금리 / 수익률 곡선

국채 금리와 수익률 곡선 변수를 핵심 모델의 확장으로 평가했습니다.

기존의 주식·변동성·신용 Feature 대비 일관된 OOS 증분 예측 가치를 제공하지 못했습니다.

**결정: 최종 명세에서 제외.**

이는 금리가 경제적으로 중요하지 않다는 의미가 아닙니다.

---

## 은행 / 유동성

2023년 미국 은행 위기 이후 은행 및 유동성 지표를 평가했습니다.

동일한 purged walk-forward OOS 프레임워크에서 핵심 17-Feature 모델 대비 일관된 증분 예측 가치를 제공하지 못했습니다.

**결정: 제외.**

2023년 은행 위기는 모델 Risk Score를 일시적으로 끌어올렸지만, 이 프로젝트의 시장 전반 Stress Event 정의를 충족하지 못했습니다.

해당 에피소드를 양성 사건으로 만들기 위해 타깃을 사후적으로(post hoc) 재정의하지 않았습니다.

---

## 시장 폭(Market Breadth) — RSP / SPY

SPY 대비 RSP를 사용한 주식시장 폭 확장을 평가했습니다.

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

시장 폭 확장은 OOS 성능을 개선하지 못했습니다.

**결정: 제외.**

---

## 비트코인

확장 모델에 다른 평가 기간이 적용되는 것을 피하기 위해, 비트코인 관련 Feature는 2014년 이후의 공통 샘플에서 평가했습니다.

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

비트코인은 여러 스트레스 기간에 반응했지만, 이 프레임워크에서는 추가해도 조기경보 성능이 실질적으로 개선되지 않았습니다.

**결정: 제외.**

---

# 16. 신용 스프레드 대리 변수(Proxy)

신용 변수는 다음과 같습니다.

**Moody's Seasoned Baa 회사채 수익률 − 미국 10년 국채 고정만기(Constant Maturity) 금리**

이는 **Baa–Treasury 신용 스트레스 대리 변수**입니다.

ICE BofA High Yield OAS로 설명해서는 안 됩니다.

글로벌 금융위기 같은 주요 과거 스트레스 기간을 검증에 포함할 수 있도록 긴 이력을 가진 신용 대리 변수를 사용했습니다.

---

# 17. API

| 엔드포인트 | 목적 |
|---|---|
| `GET /health` | API 상태 확인 |
| `GET /api/latest` | 최신 시장 데이터, MSI 및 Risk Score |
| `GET /api/shap` | 최신 XGBoost SHAP 요인 |
| `GET /api/historical` | 과거 Walk-forward OOS 시계열 |
| `GET /api/validation` | 주 OOS 검증 결과 |
| `GET /api/multi-horizon-validation` | 1D / 5D / 10D / 20D 검증 결과 |

---

# 18. 기술 스택

### 머신러닝 / 데이터

- Python
- pandas
- NumPy
- scikit-learn
- XGBoost
- SHAP

### 백엔드

- FastAPI
- Uvicorn

### 프론트엔드

- Next.js
- React
- TypeScript
- Tailwind CSS
- Recharts

### 시장 데이터

- Yahoo Finance
- FRED

---

# 19. 로컬 개발 환경

## 백엔드

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

상태 확인:

```text
http://localhost:8000/health
```

## 프론트엔드

별도의 터미널을 열어 실행합니다.

```bash
cd market-stress-early-warning/frontend

npm install
npm run dev
```

대시보드:

```text
http://localhost:3000
```

---

# 20. 한계

- Risk Score는 보정된 사건 발생 확률이 아닙니다.
- 타깃은 **미국 금융시장 전반의 스트레스**를 나타내며, 모든 종류의 금융 사건을 포괄하지 않습니다.
- 신용 스트레스는 ICE BofA HY OAS가 아닌 장기 이력의 Baa–Treasury 대리 변수로 표현됩니다.
- 과거 성능은 purged walk-forward OOS 예측에 기반합니다.
- 현재 SHAP은 과거 OOS 모델이 아닌 학습된 배포 모델을 설명합니다.
- 경보 지속성 분석은 실험적 진단 지표이며 표준 분류 지표인 FAR와 혼동해서는 안 됩니다.
- Feature 확장 결과는 여기서 사용된 특정 변수 정의, 데이터 가용성, 샘플 기간, 검증 프레임워크에 따라 달라질 수 있습니다.
- 과거 위기에서의 성능이 미래 위기의 탐지를 보장하지 않습니다.
- 이 시스템은 개별 종목 매매 신호나 직접적인 마켓 타이밍 전략이 아닙니다.

---

# 21. 연구 원칙

> **방법론적 타당성이 모델 복잡도나 Feature 개수보다 우선합니다.**

이 프로젝트는 다음을 의도적으로 구분합니다.

```text
현재 스트레스          → Market Stress Index
미래 경보              → Market Stress Risk Score
모델 설명              → SHAP
OOS 증분 정보          → LOFO
```

추가 변수는 동일한 누수 방지 Out-of-Sample 프레임워크에서 방어 가능한 증분 가치를 입증한 경우에만 유지됩니다.

---

# 요약

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

따라서 XGBoost를 단순히 "가장 성능이 좋은 모델"이라고 주장하지 않습니다.

또한 모델의 raw output에서 calibration 문제가 확인되었기 때문에 웹사이트에서는 이를 실제 발생확률이 아니라 **Market Stress Risk Score**라고 표현합니다.

SHAP은 현재 모델 출력의 주요 원인을 설명하고, LOFO 분석은 각 feature가 다른 변수들을 통제한 상태에서 실제 OOS 예측력에 추가 정보를 제공하는지를 검증합니다.

금리/수익률곡선, Banking/Liquidity, Market Breadth, Bitcoin 관련 변수도 추가 검증했지만 동일한 OOS 환경에서 일관된 증분 예측력을 확인하지 못해 최종 17개 feature에서는 제외했습니다.

이 프로젝트의 핵심 원칙은:

> **변수나 모델의 개수를 늘리는 것보다 실제 Out-of-Sample 환경에서 검증 가능한 방법론적 타당성을 우선하는 것**

입니다.

---

# 부록. 유사 프로젝트 및 참고 자료

GitHub와 학술 자료를 조사한 결과(2026-10-15 기준), 이 프로젝트처럼 **주식·변동성·신용 세 채널로 스트레스 지수를 구축하고, purged walk-forward로 검증하며, XGBoost와 SHAP을 대시보드로 서빙하는 구성을 모두 갖춘 공개 저장소는 확인되지 않았습니다.** 구성 요소별로 참고할 만한 저장소를 정리합니다.

## 1. 시장 스트레스 조기경보

| 저장소 | ★ | 비교 포인트 |
|---|---:|---|
| [mhsu2112/systemic-risk-dashboard](https://github.com/mhsu2112/systemic-risk-dashboard) | 1 | 신용시장 지표 12개를 FRED와 Yahoo Finance에서 수집해 Green/Amber/Red 신호등과 BASE/WATCH/ELEVATED 상태로 표시. 이 프로젝트의 LOW/WATCH/ELEVATED/HIGH 구간과 유사한 발상이나, ML 없이 규칙 기반 임계값 사용 |
| [Mansi2801-dev/AI-Powered-Market-Stress-Early-Warning-System](https://github.com/Mansi2801-dev/AI-Powered-Market-Stress-Early-Warning-System) | 0 | 호가창 데이터로 미래 스트레스 점수를 Transformer로 예측하고 NORMAL/WARNING/HIGH/CRITICAL 4단계로 분류. "미래 스트레스 점수 + 구간 분류" 구조가 유사 |
| [Abhay-lad/Financial-Market-Stress-Early-Warning-](https://github.com/Abhay-lad/Financial-Market-Stress-Early-Warning-) | 0 | 인도 시장의 유동성·변동성 지표 기반 조기경보. 이 프로젝트의 Korea 파이프라인과 같은 "타 시장 적용" 사례 |

## 2. 금융 스트레스 지수(FSI) 구축

| 저장소 | ★ | 비교 포인트 |
|---|---:|---|
| [onurpolat1/Financial-Stress-Index-for-Turkey](https://github.com/onurpolat1/Financial-Stress-Index-for-Turkey) | 2 | ECB의 CISS 방법론으로 일별 FSI 구축(R). 이 프로젝트의 동일 가중 Z-score 평균보다 정교한 상관 가중 결합 방식 |
| [priyadamodar/Financial-Stress-Index](https://github.com/priyadamodar/Financial-Stress-Index) | 1 | PCA로 FSI 산출. 세인트루이스 연준 STLFSI와 같은 접근 |
| [luigi-piva/turbulence-index](https://github.com/luigi-piva/turbulence-index) | 0 | Kritzman & Li의 Turbulence Index를 look-ahead 없이 구현하고 정직한 백테스트를 강조. 이 프로젝트의 past-only 롤링 Z-score 원칙과 가장 가까움 |
| [mrbcuda/stressr](https://github.com/mrbcuda/stressr) | 9 | 클리블랜드 연준 FSI 수집·시각화 R 패키지 |

## 3. 위기·침체·붕괴 예측 ML

| 저장소 | ★ | 비교 포인트 |
|---|---:|---|
| [tzhangwps/Recession-Predictor](https://github.com/tzhangwps/Recession-Predictor) | 41 | FRED 거시 지표로 미국 경기침체 확률 예측. 이 분야에서 가장 많이 참조되는 개인 저장소 |
| [Quant-Projects/Recession-Prediction](https://github.com/Quant-Projects/Recession-Prediction) | 3 | 3개월/6개월/1년 다중 horizon 예측. 이 프로젝트의 1D/5D/10D/20D 다중 기간 검증과 같은 구조 |
| [nandini0901/stock_market_crash_prediction](https://github.com/nandini0901/stock_market_crash_prediction) | 0 | Random Forest + XGBoost 붕괴 확률을 Streamlit 대시보드로 서빙 |

## 4. 레짐 탐지 (비지도 학습 대안)

- [cward0401/market-regime-hmm](https://github.com/cward0401/market-regime-hmm), [dalilaikannan/market-regime-hmm](https://github.com/dalilaikannan/market-regime-hmm): SPY + VIX로 Gaussian HMM 레짐 탐지. 이 프로젝트와 동일한 입력으로 지도학습 대신 비지도 접근을 사용
- [sonalrajapaksha/market_regime_hmm](https://github.com/sonalrajapaksha/market_regime_hmm): HMM 레짐 확률을 FastAPI로 서빙하고 Docker Compose, 드리프트 감지까지 포함. 서빙 구조가 이 프로젝트와 가장 유사

## 5. 방법론 참고 라이브러리

- [eslazarev/purged-cross-validation](https://github.com/eslazarev/purged-cross-validation) (57★): purging, embargo, combinatorial purged CV를 scikit-learn 호환으로 구현. 이 프로젝트의 label-overlap purge를 라이브러리로 대체할 때 참고 가능
- [hudson-and-thames/mlfinlab](https://github.com/hudson-and-thames/mlfinlab) (4.9k★): López de Prado 방식의 purged K-fold, 메타 레이블링 등 금융 ML 표준 도구
- [TommasoBelluzzo/SystemicRisk](https://github.com/TommasoBelluzzo/SystemicRisk) (192★, MATLAB): Absorption Ratio, CATFIN, 버블 탐지 등 학술적 시스템 리스크 지표 모음. 변수 확장 아이디어의 출처로 유용
- [Boulder-Investment-Technologies/lppls](https://github.com/Boulder-Investment-Technologies/lppls) (478★): 버블 붕괴 시점을 추정하는 LPPLS 모델

## 6. 관련 학술 자료

- [BIS Working Paper 1250](https://www.bis.org/publ/work1250.pdf): 시장 상태 지표에 Random Forest를 적용해 시장 스트레스를 예측. VIX 외에 보완 정보가 존재한다는 결론
- [IWH/Bundesbank: Early Warning Models for Systemic Banking Crises](https://www.iwh-halle.de/publikationen/detail/an-evaluation-of-early-warning-models-for-systemic-banking-crises-does-machine-learning-improve-pre/): ML이 in-sample에서는 우세하지만 recursive out-of-sample에서는 logit이 더 낫다는 결과. 이 프로젝트가 XGBoost를 무조건적 우위 모델로 두지 않는 입장과 일치
- [St. Louis Fed Financial Stress Index 2.0](https://www.stlouisfed.org/on-the-economy/2020/march/financial-stress-index-version-2): 18개 주간 시계열의 제1주성분으로 FSI를 구성하는 방법론
- [Cleveland Financial Stress Index](https://fedinprint.org/item/fedcwp/39914/original): 신용·외환·주식·은행간 시장을 동적 가중치로 결합해 스트레스 발생 원인을 추적하는 지수

## 종합

이 프로젝트는 FSI 구축, 지도학습 기반 조기경보, 누수 방지 검증, 설명 가능성, 웹 서빙을 한 곳에 결합했다는 점에서 공개 저장소 중 드문 조합입니다. 가장 가까운 비교 대상은 신용지표 신호등 대시보드인 mhsu2112/systemic-risk-dashboard와, past-only 원칙을 공유하는 luigi-piva/turbulence-index입니다.

---

# 부록 2. 사후 검증 사례: 2026-10-15 한국 증시 급락

## 사건 개요

2026년 10월 15일 코스피는 전일 대비 7.57% 하락한 5,554.22로 마감했고, 코스피·코스닥 모두 서킷브레이커가 발동됐습니다. 언론은 10월 14일 발표된 미국 9월 CPI가 예상을 웃돈 인플레이션 충격, 미국 AI·반도체주 급락, 외국인 대규모 순매도를 원인으로 보도했습니다. 코스피는 6월 22일 고점(9,114.5) 대비 39.1% 하락한 수준이었습니다.

## 검증 질문

> 이 시스템의 결과를 이 사건의 예측에 적용할 수 있었는가?

**결론: 부분적으로만 가능하며, "특정일의 하루 폭락"을 맞히는 용도로는 설계되지 않은 시스템입니다.** 이 모델이 예측하는 것은 "향후 10거래일 안에 시장 전반이 Stress Event 상태(MSI가 과거 90% 분위수 초과)에 들어가는가"입니다. 이 사건은 이미 진행 중이던 스트레스 에피소드의 정점이었습니다.

## 검증 범위와 한계

검증 시점에 한국 파이프라인을 완전히 실행할 수 없었습니다.

- 한국 데이터 수집에는 `KRX_API_KEY`와 `ECOS_API_KEY`가 필요한데 로컬 환경에 없었습니다.
- VKOSPI와 한국 신용 스프레드(AA- 회사채 3년 − 국고채)는 Yahoo Finance에서 받을 수 없습니다.
- 한국 XGBoost 모델은 17개 feature 전부를 요구하므로 일부 feature만으로는 Risk Score를 산출할 수 없습니다.

따라서 아래 수치는 **시스템 전체의 출력이 아니라, 주식 채널 하나만 이 시스템의 공식으로 재계산한 결과**입니다.

| 구분 | 내용 |
|---|---|
| 시스템에서 가져온 것 | `build_korea_stress_index.py`의 주식 채널 공식(21일 수익률 부호 반전 → 전일까지의 252일 과거 분포로 Z-score 표준화), `build_korea_target.py`의 과거 90% 분위수 임계값 개념 |
| 시스템 밖에서 가져온 것 | 입력 데이터. KRX API 대신 Yahoo Finance의 KOSPI 지수(^KS11)와 KODEX 200 ETF(069500.KS)를 KOSPI200 대리 변수로 사용 |
| 실행하지 않은 것 | 세 채널 합산 한국 MSI, 한국 XGBoost 모델의 Risk Score |

## 주식 채널 사전 신호

KOSPI 지수 기준. KODEX 200 ETF로 계산한 결과도 거의 동일했습니다.

| 날짜 | KOSPI | 일간 수익률 | 20일 수익률 | 주식 Z-score | 과거 90% 분위수 |
|---|---:|---:|---:|---:|---:|
| 10-07 | 6,803.9 | -2.0% | +1.7% | 0.29 | 1.46 |
| 10-08 | 6,625.9 | -2.6% | -5.3% | 0.61 | 1.46 |
| 10-12 | 6,384.2 | -3.7% | -8.2% | 1.18 | 1.46 |
| 10-13 | 6,035.4 | -5.5% | -14.4% | **1.50** | 1.46 |
| 10-14 | 6,008.8 | -0.4% | -14.6% | **1.60** | 1.46 |
| 10-15 | 5,554.2 | -7.6% | -19.6% | **2.04** | 1.46 |

## 해석

- **주식 채널만으로도 10월 13일에 Stress Event 조건을 넘었습니다.** 13일에 5.5% 급락이 있었으므로 VKOSPI 채널도 함께 상승했을 가능성이 높고, 한국 모델의 10일 Risk Score는 13~14일 시점에 ELEVATED 이상이었을 것으로 추정됩니다. 이 추정은 모델 출력이 아니라 주식 채널 수치에 근거한 추론입니다.
- **"조기" 경보였는지는 확인되지 않았습니다.** 10월 7~8일의 주식 Z-score는 0.3~0.6으로 임계값에 한참 못 미쳤습니다. 그 시점에 경보가 났으려면 VKOSPI나 신용 스프레드가 먼저 움직였어야 하는데, 해당 데이터가 없어 검증하지 못했습니다. 12~13일의 급락 이후에야 경보가 켜졌다면 사실상 이미 벌어진 일을 추인한 것에 가깝습니다.
- **미국 모델은 선행 정보를 제공하지 못했습니다.** 10월 14일 미국장 종가 기준 10-Day Risk Score는 20.6(LOW)이었고, 한국 급락의 직접 원인이 바로 그 14일의 미국 CPI 충격이었습니다. 미국 모델은 미국 시장 스트레스를 대상으로 설계됐으므로 한국 시장 적용 자체가 범위 밖입니다.
- **지속 하락장에서의 구조적 한계가 드러났습니다.** 코스피는 한 달간 16%, 고점 대비 39% 하락한 상태였습니다. 임계값이 과거 분포를 따라 계속 올라가는 구조에서는 모델이 "스트레스가 커진다"는 신호를 반복할 수는 있어도 서킷브레이커 같은 꼬리 사건의 발생일은 짚지 못합니다.

## 완전한 검증을 위한 절차

1. `.env`에 `KRX_API_KEY`와 `ECOS_API_KEY`를 설정합니다.
2. `src/korea/` 파이프라인(수집 → 스트레스 지수 → 타깃 → feature)을 실행합니다.
3. 저장된 `models/korea/xgboost_10d_latest.joblib`로 10월 5일~14일 구간의 Risk Score를 재학습 없이 산출합니다.

이 절차를 거치면 "사건 며칠 전에 모델이 실제로 몇 점을 냈는지"를 확인할 수 있습니다.

## 주의

이 검증은 사후(hindsight) 분석입니다. 사건이 일어난 뒤 돌아보면 신호가 뚜렷해 보이지만, 같은 수준의 점수가 급락으로 이어지지 않은 경우도 과거에 많았습니다. 이 프로젝트의 경보 지속성 분석에서 XGBoost 경보 1일 이상 중 실제 스트레스로 이어진 비율은 38%였습니다. 단일 사건으로 모델의 유효성을 판단해서는 안 됩니다.

## 출처

- [뉴스핌: '검은 목요일' 코스피·코스닥 7%대 급락 마감](https://www.newspim.com/news/view/20261015001061)
- [글로벌이코노믹: 코스피, 전방위 악재에 6%대 급락](https://www.g-enews.com/article/Securities/2026/10/202610150915015997923c501012_1)
- [Korea JoongAng Daily: Stocks plunge as circuit breakers hit Kospi, Kosdaq](https://www.koreajoongangdaily.com/business/stocks-plunge-as-circuit-breakers-hit-kospi-kosdaq-for-first-time-in-over-two-months/12922302)
- [Investing.com: KOSPI 8% plunge triggers circuit breaker](https://uk.investing.com/news/stock-market-news/kospi-hits-sixmonth-low-as-8-plunge-triggers-circuit-breaker-4911218)
- [TradingKey: Why Did KOSPI Plunge? 16% drop over the past month](https://www.tradingkey.com/analysis/stocks/us-stocks/262218135-kospi-skhynix-samsung-ai-skhy-hbm-dram-tradingkey)
