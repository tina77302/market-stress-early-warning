# Market Stress Early Warning System

AI 기반 미국 금융시장 스트레스 조기경보 시스템입니다.
SPY(주가), VIX(변동성), Credit Spread(신용 위험)를 결합한 복합 Market Stress Index(MSI)를 산출하고,
XGBoost + Walk-Forward Validation을 통해 **향후 10 영업일 내 스트레스 이벤트 발생 확률**을 예측합니다.

---

## 📦 프로젝트 구조

```
market-stress-early-warning/
├── run_pipeline.py        # [2~12단계] 전체 파이프라인 일괄 실행
├── requirements.txt       # Python 의존성
├── .env.example           # 환경변수 템플릿 (FRED API Key 등)
├── data/
│   ├── raw/               # [2] 원본 수집 데이터
│   ├── processed/         # [3] 정제 데이터, OOS 예측 결과
│   └── features/          # [4~7] MSI, 타깃, 피처 행렬
├── models/saved/          # [8~10] 저장된 모델 가중치 (.joblib)
├── src/
│   ├── config.py          # 공통 경로 및 하이퍼파라미터 설정
│   ├── data/
│   │   ├── fetcher.py     # [2] SPY, VIX, Credit Spread 수집
│   │   └── cleaner.py     # [3] 결측치 처리 및 정제
│   ├── features/
│   │   ├── stress_index.py  # [4] Market Stress Index (MSI)
│   │   ├── targets.py       # [5+6] Stress Event 정의 & 10D Target
│   │   └── engineering.py   # [7] 피처 엔지니어링 (17개 ML 피처)
│   ├── models/
│   │   ├── logistic.py      # [8] Baseline Logistic Regression
│   │   ├── xgboost_model.py # [9] Main XGBoost Classifier
│   │   ├── walk_forward.py  # [10] Expanding Window Walk-Forward
│   │   └── evaluation.py    # [11+12] 성능평가 & Historical 분석
│   └── api/
│       └── main.py          # [14] FastAPI 백엔드 (3개 엔드포인트)
├── tests/
│   └── test_environment.py  # [1] 환경 무결성 검증 테스트
└── frontend/                # [15] React/Next.js 대시보드
    ├── src/app/
    │   ├── page.tsx           # PAGE 01 - Market Risk Intelligence
    │   └── validation/page.tsx # PAGE 02 - Model Validation
    └── package.json
```

---

## 🚀 실행 방법

### 1. 환경 설정

```powershell
# 가상환경 활성화
.\venv\Scripts\Activate.ps1

# (선택) FRED API 키 설정
cp .env.example .env
# .env 파일에 FRED_API_KEY 입력 (없어도 자동 Fallback으로 동작)
```

### 2. 전체 파이프라인 실행 [2~12단계]

```powershell
python run_pipeline.py
```

### 3. FastAPI 서버 실행 [14단계]

```powershell
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

API 확인: http://127.0.0.1:8000/docs

### 4. Next.js 대시보드 실행 [15단계]

```powershell
cd frontend
npm run dev
```

대시보드: http://localhost:3000

---

## 📊 주요 API 엔드포인트

| Endpoint | 설명 |
|---|---|
| `GET /health` | 서버 상태 확인 |
| `GET /api/latest` | 최신 날짜 위험 지표 및 예측값 |
| `GET /api/historical?days=500` | 시계열 과거 데이터 (차트용) |
| `GET /api/validation` | 모델 성능 지표 & 위기 사건 분석 |

---

## 📈 모델 성능 (Walk-Forward OOS 결과)

| 모델 | ROC-AUC | PR-AUC | F1 Score |
|---|---|---|---|
| Logistic Regression (Baseline) | **0.8935** | 0.7742 | 0.6630 |
| XGBoost (Main Model) | 0.8738 | 0.7367 | **0.6734** |

---

## 🏛️ 검증된 과거 위기 사건 (Historical Backtest)

| 위기 이벤트 | Max Risk Prob | High Risk Days |
|---|---|---|
| 2008 Financial Crisis | **98.2%** | 167/392일 |
| 2020 COVID-19 Crash | **98.5%** | 34/64일 |
| 2022 Inflation Shock | **98.7%** | 116/216일 |
| 2023 SVB Banking Stress | 68.9% | 3/43일 |
