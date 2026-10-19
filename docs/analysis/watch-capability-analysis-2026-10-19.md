## 결론

ZSCORE WATCH는 **현재 스트레스 수준을 설명하는 단순·독립 기준선**으로 유용하고, 기존 대시보드의 XGBoost WATCH는 **향후 10거래일 스트레스 감지 범위를 넓히는 대신 경보 부담이 커지는 기준**입니다. 두 신호는 의미와 임계값이 다르므로 별도 축으로 표시하는 것이 적절합니다.

현재 브랜치의 Z-score 구현은 **계산 모듈·CLI·단위 테스트 단계**입니다. API, 대시보드, 운영 배치에 연결되지 않았습니다. 대시보드도 요청 시 저장된 데이터와 모델을 읽는 구조로, 이 코드만으로 지속적인 자동 감시·통지까지 구현됐다고 볼 수 없습니다.

분석 기준일: **2026-10-19 (Asia/Seoul)**. 대상: `feature/zscore-warning`, 커밋 [`db94e28`](https://github.com/tina77302/market-stress-early-warning/commit/db94e280bd3729885f9ebe81a74821f71d19b12f). 당시 `main`의 `ce633d5` 대비 추가된 파일은 `src/models/zscore_warning.py`, `tests/test_zscore_warning.py` 두 개입니다.

> 범위: 소스와 저장소에 포함된 미국 과거 데이터를 검토했습니다. 제공된 브랜치에는 `LIVE MONITORING`이라는 별도 이름의 화면/모듈이 없어, 이 분석에서는 `/`, `/us`, `/korea`의 현재 위험 조회 기능을 의미하는 것으로 해석했습니다. 실제 배포 주소, 서버의 최신 데이터, cron 설치 여부, 외부 알림 운영 상태는 확인하지 않았습니다. 한국 시장은 계산 경로를 검토했으며 실증 성능 수치는 미국 자료에 한정합니다.

## 1. 구현과 watch capability 비교

| 항목 | ZSCORE WATCH | 기존 대시보드 / LIVE MONITORING으로 해석한 기능 |
| --- | --- | --- |
| 감시 대상 | 당일 MSI가 자신의 과거 분포 대비 높은지 | 최신 17개 특징을 이용한 XGBoost 10거래일 위험 점수 |
| 규칙 | `MSI(t) >= Q80(MSI(<t))` | 미국: LOW <30, WATCH 30–<50, ELEVATED 50–<70, HIGH ≥70. 한국: 원시 모델 출력 ≥0.50 경고 |
| 정보 시점 | 기준 분위수는 `shift(1)`로 현재 관측을 제외. 최소 과거 유효 MSI 252개 필요 | 최신 특징 날짜로 배포 모델 추론. 과거 차트는 저장된 walk-forward OOS 예측 |
| 임계값의 시간 범위 | MSI 구성 채널은 과거 252일 rolling Z-score, **WATCH 임계값은 전체 과거 expanding 80분위수** | 표시 구간은 고정 점수 기준. 점수는 보정된 사건 발생 확률이 아님 |
| 산출물 | 미국/한국 CSV, `latest_zscore_warning()`의 날짜·MSI·임계값·활성 여부 | 미국/한국 최신 API, 과거 차트, SHAP 설명 |
| 실제 연결 | 모델 파일 없이 계산 가능. API·화면 연결 없음 | 현재 위험 API는 연결돼 있으나 Z-score 결과를 사용하지 않음 |
| 자동 갱신 | 모듈 직접 실행 필요 | 홈은 최초 조회와 오류 재시도, 미국/한국 상세 화면은 mount 시 1회 조회 |
| 지속 감시·통지 | 상태 전환 기록, 연속 경보 정책, 알림 전송 경로 없음 | polling/SSE/WebSocket, 경보 이력·확인·해제·전송 경로를 관련 코드에서 확인하지 못함 |

구현 근거: [Z-score 규칙](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/src/models/zscore_warning.py#L18-L79), [MSI 구성](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/src/features/stress_index.py#L73-L127), [미국 최신 위험 API](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/src/api/main.py#L170-L253), [한국 경고 규칙](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/src/api/main.py#L705-L728), [미국 점수 구간](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/frontend/src/app/us/page.tsx#L72-L103).

### 선행 경보라는 표현의 한계

- 같은 과거 표본으로 만든 Q80은 Q90보다 낮습니다. 따라서 현재 Stress Event가 발생한 날에는 WATCH도 켜질 수 있지만, **반드시 며칠 먼저 켜진다는 보장은 없습니다**. 하위 임계값이라는 사실과 미래 사건 예측력은 별도로 검증해야 합니다.
- `ZScore_Warning`은 합성 MSI의 과거 분위수 경보입니다. 단일 자산 Z-score가 2 또는 3을 넘는 규칙도, 미래 10일 사건 확률도 아닙니다.
- expanding 임계값은 긴 과거 이력을 유지하므로 새로운 시장 국면에 적응하는 속도가 느릴 수 있습니다. 이는 설계상 특성이며, rolling/감쇠 방식 변경은 별도의 검증이 필요합니다.

근거: [90분위수 사건 및 미래 10일 정답](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/src/features/targets.py#L61-L109), [80분위수 WATCH](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/src/models/zscore_warning.py#L59-L79).

## 2. 미국 과거 자료로 확인한 감지 성능

공통 평가 기간은 **2006-08-09~2026-09-16, 5,057개 거래 관측일**입니다. 전체 과거 MSI로 각 시점 이전의 Q80/Q90을 재계산하고, 저장된 `Prob_XGBoost`와 같은 날짜에 결합했습니다. XGBoost 기준은 실제 미국 화면처럼 `round(Prob_XGBoost × 100, 1)`에 30/50 구간을 적용했습니다. `WATCH+`는 WATCH·ELEVATED·HIGH를 모두 포함하며 WATCH 구간만을 뜻하지 않습니다.

정답은 **다음 1~10개 거래 관측 중 Q90 Stress Event가 한 번이라도 발생하는지**입니다. 이미 스트레스가 진행 중인 날의 반복 경보가 선행 감지 성능을 높여 보이지 않도록, 주요 비교는 **당일 비스트레스 4,562일**로 제한했습니다. 이 중 미래 10일 정답 양성은 **420일**, 음성은 **4,142일**입니다.

| 기준 | 경보일 / 평가일 | 경보 적중률 Precision | 감지율 Recall | 비사건일 오경보율 FPR |
| --- | ---: | ---: | ---: | ---: |
| ZSCORE WATCH | 462 / 4,562 (10.1%) | 213 / 462 = **46.1%** | 213 / 420 = **50.7%** | 249 / 4,142 = **6.0%** |
| XGBoost WATCH+ (표시 점수 ≥30) | 1,132 / 4,562 (24.8%) | 288 / 1,132 = **25.4%** | 288 / 420 = **68.6%** | 844 / 4,142 = **20.4%** |
| XGBoost ELEVATED+ (표시 점수 ≥50) | 674 / 4,562 (14.8%) | 234 / 674 = **34.7%** | 234 / 420 = **55.7%** | 440 / 4,142 = **10.6%** |

해석: ZSCORE WATCH는 경보 부담이 작고 적중률이 높았으며, XGBoost WATCH+는 더 많은 미래 양성일을 감지했습니다. 이는 **현재 임계값에서의 운영 선택지 비교**입니다. 경보 빈도가 다르므로 알고리즘 자체의 우열로 일반화할 수 없습니다. 같은 경보 예산에서의 비교는 별도 개발 구간에서 기준을 정한 뒤 미사용 기간에서 평가해야 합니다.

당일 스트레스 여부를 구분하지 않은 전체 5,057일에서는 ZSCORE WATCH Precision 70.7%, Recall 76.6%였습니다. 위 주요 표의 46.1%·50.7%와 차이가 있으므로, 전체 표본 수치만으로 순수 선행 감지 능력을 주장하지 않는 것이 좋습니다.

### 에피소드 민감도 점검

직전 **20개 관측일 동안 Stress Event가 없었다가 다시 발생한 경우**만 새 에피소드로 정의하면 공통 기간에 24회입니다. 그 발생일 직전 10거래일 안의 경고 유무를 확인했습니다.

| 기준 | 미리 경고한 에피소드 | 감지된 에피소드의 창 내 첫 경고 선행일 중앙값 |
| --- | ---: | ---: |
| ZSCORE WATCH | 21 / 24 (87.5%) | 5거래일 |
| XGBoost WATCH+ | 24 / 24 (100.0%) | 6거래일 |
| XGBoost ELEVATED+ | 21 / 24 (87.5%) | 6거래일 |

**24회라는 작은 표본과 위 에피소드 정의에 의존하는 탐색 결과**입니다. 선행일은 최대 10일 창 안에서만 측정했고, 경고한 에피소드만 중앙값에 포함했습니다. 100%는 이 표본에서의 관측이며 미래 감지 보장이 아닙니다. 일별 표의 겹치는 10일 정답들도 독립 표본은 아닙니다.

### 자료 검증과 적용 한계

- 날짜는 오름차순·중복 없음. 평가 결합은 1:1이며 필요한 값에 결측/비유한값이 없음을 확인했습니다.
- Q90 및 미래 10일 정답을 재계산했으며 저장된 `targets.csv`, 평가 기간의 `Actual_Target`과 모두 일치했습니다. OOS와 현 MSI의 최대 절대 수치 차이는 약 `2.01e-5`이나 Q80/Q90 분류 변화는 0건입니다.
- 이 비교는 **저장된 OOS 예측을 재사용한 과거 재생**입니다. 모델 재학습, 배포 API 응답, 당시 실제 수집 시각·발표 지연·원자료 개정 이력까지 검증한 운영 백테스트는 아닙니다.
- 저장소 MSI의 끝은 **2026-10-05**, OOS 예측의 끝은 **2026-09-16**입니다. 서로 다른 목적의 자료이며 최신 배포 서버의 신선도를 뜻하지 않습니다. OOS를 현재 관측일 데이터로 대체해서도 안 됩니다.
- 한국 시장에 대한 같은 성능 수치는 산출하지 않았습니다. 미국 결과를 한국 시장에 적용할 근거는 이번 범위에 없습니다.

자료: [MSI 스냅샷](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/data/features/market_stress_index.csv), [정답 스냅샷](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/data/features/targets.csv), [OOS 예측 스냅샷](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/data/processed/oos_predictions.csv).

## 3. 실제 watch 운영을 막는 공백과 우선순위

| 우선순위 | 확인한 공백과 영향 | 제안 및 완료 기준 |
| --- | --- | --- |
| P1 | Z-score 파일 생성이 전체 파이프라인에 포함되지 않고 최신/과거 API도 결과를 노출하지 않음. 브랜치 기능이 화면에 도달하지 않음 | MSI 생성 뒤 미국/한국 경보를 계산하고, API·화면에 별도 이름으로 표시. 같은 날짜의 CLI·API·화면 신호가 일치해야 함 |
| P1 | 한국 30분 cron은 `krx vkospi ecos` 원천 다운로드만 수행. MSI/특징/경보 갱신으로 이어지지 않음 | 수집→정제→MSI/특징→경보·고정 배포 모델 추론용 자료→게시 순서를 연결. 각 단계 성공과 공통 관측일을 확인한 완성본만 게시. 반복 추론을 위한 모델 재학습은 별도 주기로 관리 |
| P1 | API 성공·`/health`의 `ok`와 데이터 신선도가 분리되지 않음. 관측 날짜만 있고 수집/계산 시각이나 시장 달력 기반 stale 판단이 없음 | `data_asof`, `fetched_at`, `computed_at`, 소스별 관측일·신선도·채움 여부, 모델/규칙 버전을 반환. 휴장·발표 지연을 고려해 STALE/UNKNOWN을 화면에 표시 |
| P1 | `latest_zscore_warning()`은 마지막 MSI가 결측이면 과거의 마지막 유효 경보를 반환하며 stale 사유를 주지 않음 | 원래 최신 관측일과 마지막 유효 신호일을 모두 제공. 최신 결측·데이터 부족은 OFF와 구분하고, 이전 값 사용 여부를 명시 |
| P2 | 상세 화면은 최초 1회만 조회. 홈의 재시도도 주기적 갱신이 아님 | 명시적 새로고침과 데이터 주기에 맞는 polling/재연결 정책을 추가. 페이지 유지 중 새 관측이 반영되고 오류·지연·최종 성공 시각이 보이는지 확인 |
| P2 | 알림 수명주기와 지속성 정책 부재 | signal 계산과 별도로 상태 전환·이력·중복 억제·확인/해제·전송 실패 재시도를 설계. ON 유지 중 반복 발송을 막고 새 에피소드·상향 전환의 처리 기준을 정함. 지속일수 조건은 지연과 누락 비용까지 검증한 뒤 선택 |
| P2 | 미국/한국 상세 화면은 최신·과거·SHAP를 `Promise.all`로 묶고 하나의 응답 실패에도 조회 전체를 실패 처리 | 보조 SHAP/과거 조회가 실패해도 유효한 최신 핵심 경보를 표시하도록 부분 실패를 분리 |
| P2 | Z-score 함수는 결측은 구분하지만 비유한값·단조롭지 않은 인덱스 등 입력 계약이 충분하지 않음. CLI에서만 정렬/중복 검사 수행 | 재사용 함수 경계에서도 유효 날짜·유한값·중복·임계값 파라미터와 충분한 유효 표본을 검증하고 품질 상태를 전달 |

근거: [파이프라인](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/run_pipeline.py#L24-L72), [cron 기본 주기/명령](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/cli/schedule_batch.sh#L26-L44), [다운로드 명령](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/cli/fetch_korea_data.sh#L105-L115), [현재 health](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/src/api/main.py#L158-L163), [홈 조회](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/frontend/src/app/page.tsx#L90-L123), [미국 상세 조회](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/frontend/src/app/us/page.tsx#L126-L156), [한국 상세 조회](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/frontend/src/app/korea/page.tsx#L73-L103), [마지막 유효 값 선택](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/src/models/zscore_warning.py#L82-L97).

## 4. 확인한 테스트와 추가 수용 기준

기존 `tests/test_zscore_warning.py`: **9개 통과**. 초기 252개 warm-up NaN, 과거 80분위수 규칙, 미래 변형이 과거 결과를 바꾸지 않는 성질, Q80≤Q90, 한국 컬럼, 결측 처리를 확인합니다. 약 20% 경보율 테스트는 합성 정규 표본에 대한 검사이며 실제 시장의 경보 빈도를 보장하지 않습니다. [테스트 소스](https://github.com/tina77302/market-stress-early-warning/blob/db94e280bd3729885f9ebe81a74821f71d19b12f/tests/test_zscore_warning.py).

추가 재현 결과:

- 마지막 `2026-10-05` MSI만 NaN으로 바꾸면 latest helper는 `2026-10-02`를 반환합니다. fallback 자체는 함수의 명세와 일치하지만 실시간 감시에 쓸 때 freshness 계약이 필요합니다.
- 낮은 MSI가 이어지다 급등하는 합성 경로에서, 직전 10일 WATCH가 0회여도 급등 당일 WATCH와 Stress Event가 동시에 켜졌습니다. 항상 선행한다는 해석의 반례입니다.
- 상수 MSI 0을 300개 입력하면 warm-up 이후 WATCH가 모두 ON입니다. 동률의 `>=` 규칙 때문에 경보율이 100%가 될 수 있으므로 80분위수=항상 20% 경보라는 해석도 성립하지 않습니다.

향후 구현 완료 판정:

- [ ] 미국/한국 MSI와 Z-score 경보가 동일한 최신 관측일로 파이프라인→API→화면까지 이어진다.
- [ ] 정상 OFF, 데이터 부족, 결측, STALE, 이전 유효 값 사용을 구별한다.
- [ ] 시장 휴장·소스별 지연·부분 API 실패·중복 날짜·비유한값을 검증한다.
- [ ] 화면을 열어 둔 상태에서 새 관측이 반영되고 데이터/연결 상태가 따로 표시된다.
- [ ] 경보 최초 발생·유지·해제·재발 및 중복 전송/전송 실패를 추적할 수 있다.
- [ ] 미국/한국별 미사용 기간에서 같은 경보 예산의 Precision/Recall, 에피소드 탐지율, 선행일, 경보 지속일수를 비교한다.

권고: 현재 구현을 **관측 기반 ZSCORE WATCH + 모델 기반 10D RISK** 두 축으로 발전시키되, 우선 P1의 갱신 연결·신선도·결측 상태 계약을 완성하는 것이 좋습니다. 신호를 하나의 확률로 합치거나 단순 OR/AND가 더 좋다고 주장할 근거는 이번 분석에 없습니다.

## 5. 재현

기준 커밋의 저장소 루트에서 필요한 패키지(`pandas`, `numpy`, `python-dotenv`, 테스트용 `pytest`)를 설치한 후 `python -m pytest tests/test_zscore_warning.py -q`를 실행합니다. 아래 코드는 저장소 루트의 `watch_analysis.py`로 저장하고 `python watch_analysis.py`로 실행할 수 있습니다. `.analysis/deps`는 이번 작업의 선택적 로컬 설치 경로이며 일반 설치 환경에서는 필요하지 않습니다. 외부 시장 데이터를 새로 수집하거나 모델을 재학습하지 않습니다.

<details>
<summary>실행한 재현 코드: 공통 표본, 혼동행렬, 에피소드 및 경계 사례</summary>

~~~python
"""Run from the repository root at db94e280bd3729885f9ebe81a74821f71d19b12f."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

# Optional local dependency directory used only by this analysis workspace.
sys.path[:0] = [str(Path.cwd() / '.analysis/deps'), str(Path.cwd())]
from src.models.zscore_warning import add_zscore_warning, latest_zscore_warning


def read(path):
    df = pd.read_csv(path, index_col='Date', parse_dates=True)
    assert df.index.is_unique and df.index.is_monotonic_increasing
    return df


m = read('data/features/market_stress_index.csv')
t = read('data/features/targets.csv')
o = read('data/processed/oos_predictions.csv')
w = add_zscore_warning(m)
q90 = m.MSI.shift(1).expanding(min_periods=252).quantile(.90)
event = m.MSI.ge(q90).where(q90.notna()).astype(float)
truth = pd.concat([event.shift(-k) for k in range(1, 11)], axis=1).max(axis=1, skipna=False)
assert np.allclose(truth.loc[t.index], t.Target_10D, equal_nan=True)
assert truth.loc[o.index].eq(o.Actual_Target).all()
delta = (m.MSI.loc[o.index] - o.MSI).abs()
for q in [w.ZScore_Watch_Threshold, q90]:
    assert m.MSI.loc[o.index].ge(q.loc[o.index]).eq(o.MSI.ge(q.loc[o.index])).all()
print('MSI max absolute delta:', delta.max())
base = o.join(w[['ZScore_Warning']], validate='one_to_one')
base['truth'], base['event'] = truth.loc[o.index], event.loc[o.index]
assert base.notna().all().all() and np.isfinite(base.to_numpy()).all()
score = o.Prob_XGBoost.map(lambda p: round(float(p) * 100, 1))
signals = {'ZSCORE': base.ZScore_Warning.eq(1), 'XGB WATCH+': score.ge(30), 'XGB ELEVATED+': score.ge(50)}

for population, keep in [('all days', pd.Series(True, index=base.index)), ('nonstress days', base.event.eq(0))]:
    rows = []
    for name, signal in signals.items():
        p, y = signal.loc[keep], base.loc[keep, 'truth'].eq(1)
        tp, fp, fn, tn = int((p & y).sum()), int((p & ~y).sum()), int((~p & y).sum()), int((~p & ~y).sum())
        rows.append(dict(method=name, n=len(y), TP=tp, FP=fp, FN=fn, TN=tn,
                         warning_rate=p.mean(), precision=tp/(tp+fp), recall=tp/(tp+fn), FPR=fp/(fp+tn)))
    print(population)
    print(pd.DataFrame(rows).to_string(index=False))

onsets = []
for date in m.index[event.eq(1) & event.shift(1).eq(0)]:
    i = m.index.get_loc(date)
    past = m.index[max(0, i-20):i]
    if date in base.index and len(past) == 20 and past.isin(base.index).all() and event.loc[past].eq(0).all():
        onsets.append(date)
for name, signal in signals.items():
    leads = []
    for date in onsets:
        i = m.index.get_loc(date)
        fired = [10-k for k, d in enumerate(m.index[i-10:i]) if signal.loc[d]]
        if fired: leads.append(max(fired))
    print('20-day reset episodes:', name, len(leads), '/', len(onsets), 'median detected lead:', np.median(leads))

missing = m.copy()
missing.loc[missing.index[-1], 'MSI'] = np.nan
print('missing last MSI -> returned date:', latest_zscore_warning(add_zscore_warning(missing))['date'])
rng = np.random.default_rng(123)
jump = pd.DataFrame({'MSI': np.r_[rng.normal(size=400), np.full(20, -2.), 8.]}, index=pd.bdate_range('2020-01-01', periods=421))
jw = add_zscore_warning(jump)
jq90 = jump.MSI.shift(1).expanding(min_periods=252).quantile(.9)
assert jw.ZScore_Warning.iloc[-11:-1].sum() == 0
assert jw.ZScore_Warning.iloc[-1] == 1 and jump.MSI.iloc[-1] >= jq90.iloc[-1]
flat = add_zscore_warning(pd.DataFrame({'MSI': np.zeros(300)}, index=pd.bdate_range('2020-01-01', periods=300)))
assert flat.ZScore_Warning.dropna().eq(1).all()
print('sudden jump without prior watch: reproduced; flat-series warning rate:', flat.ZScore_Warning.mean())
~~~

</details>

입력 파일 SHA-256:

~~~text
market_stress_index.csv  b5ab25683987171f530a468a9bf3a261d5df8156147a791b8ec8e92d4a9b683d
targets.csv              f04c35d458c761eceb86d3165b2652931be3745ac76fe9ea59530d82fd3768fa
oos_predictions.csv      bbe9d3767ea49d6ce629f27fd3d83270043d0934993f00de32e9657e25434a33
~~~

검토 상태: **위 범위에서는 재현 결과와 구현 근거를 확인했으며, 실제 배포·발표 시점 데이터의 한계를 명시한 분석 기록입니다.** 이번 기록은 코드 수정이나 운영 감시가 활성화됐다는 의미가 아닙니다.
