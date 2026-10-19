# 발표 근거 점검: 모의투자와 운영 검증

- 점검일: 2026-10-19 (Asia/Seoul)
- 목적: 발표에서 코드로 확인한 구현, 기존 검증 보고, 미확인 성과를 구분한다.
- 발표 문서 작업 시작점: `f120a911557f6fbd70ca525ef94894cb252aa45f`.
- 기존 시스템 설명 기준: `main`의 `8d3e75f55d68dacea36925de409553f13157cbb2`.
- 모의투자·운영 구현 확인 기준: `wip/data-automation`의 **`4a75acd1e1e73e58c9cb600519401a9ca4a22bc1`**. 아래 소스 링크는 이 커밋에 고정했다.
- 연결: [전체 발표안](README.md), [김주미 대본](joomee-speaker-notes.md), [제품 완성 계획](../operations/project-completion-plan.md).

## 1. 확인 범위와 중요한 정정

발표 문서가 있는 현재 체크아웃에는 `src/paper/`와 모의투자 화면이 없다. 원격의 WIP 브랜치에는 해당 구현이 있다. 따라서 기존 문서의 “모의투자 전체 미확인”을 **“WIP 코드 확인, 운영 계정·성과·배포는 별도 확인 필요”**로 수정한다. 이번 변경으로 WIP 구현을 병합하거나 배포하지 않는다. 시연 환경이 위 커밋을 포함하는지는 발표 전에 확인해야 한다.

확인 방법은 코드·설정·추적 파일 목록·기존 보고서의 정적 대조다. 이번 작업에서 WIP 서버를 실행하거나 계정에 주문하지 않았고, 기존 보고서에 적힌 테스트·브라우저 QA를 재실행하지 않았다. 개인 계정 DB·비밀키·비공개 가격 이력을 커밋하지 않는다.

오래된 `docs/paper-trading.md`의 시장별 독립 초기자금·무비용·무환전 설명은 최신 구현과 다르다. [WIP README](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/README.md), [현행 비용 문서](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/docs/realistic-paper-trading-costs.md), [환율 정책](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/docs/delayed-fx-provider.md)과 아래 코드로 확인한다.

## 2. 투자 규칙·신호·체결

| 항목 | 확인한 내용 | 발표에서의 해석 |
| --- | --- | --- |
| 구현 유형 | 사용자가 종목·수량·BUY/SELL을 정하고 견적·비용을 검토한 뒤 제출하는 수동 모의투자 | 자동 매매 전략의 백테스트로 소개하지 않는다. |
| 대상 | 미국·한국의 지원 목록에서 검증한 주식·ETF, 정수 주식 수량 | 실제 거래 가능 목록과 시연 종목은 시연 환경에서 재확인한다. |
| 초기자금 | 새 통합 계정의 초기 기여 USD 100,000, KRW 0. USD·KRW 현금을 하나의 USD 기준 계정으로 합산 | 기존 계정이 같은 잔고로 초기화됐다고 가정하지 않는다. |
| 매매 제약 | 현금·보유 수량 확인, 공매도 불가. 매수 비용은 취득원가에 포함, 일부 매도는 평균 취득원가를 수량 비례 배분 | 레버리지·공매도 전략이나 FIFO 성과로 설명하지 않는다. |
| Risk Score와 주문 | 시장 위험·보유 노출 정보를 참고해 사용자가 판단. 확인한 주문 경로에 점수→자동 비중·진입·청산 규칙 없음 | 특정 점수에서 매수/매도한다는 규칙은 제시하지 않는다. |
| 신호 시각 | 시장 스냅샷에 관측일·추론 시각·게시 시각이 존재. 확인한 주문 저장에는 직접 연결된 신호 record ID 없음 | 해당 주문이 당시의 특정 신호를 사용했다는 입증은 확인 필요다. |
| 가격 | Yahoo/yfinance의 `auto_adjust=False` 일봉 종가. 거래소 현지 날짜의 당일 행을 제외한 완료 일봉 사용 | 지연된 과거 종가를 기준으로 한 모의 체결이다. 실시간 체결·다음 시가 체결로 표현하지 않는다. |
| 가격 검증 | 서버 견적 기본 유효기간 120초. 가격 관측 후 최대 5일은 기본 설정값이며 만료·부정확한 가격은 거부 | 120초는 견적 유효기간이며 시세가 120초 이내 데이터라는 뜻이 아니다. |
| 체결 시점 | 제출 처리 시 저장된 `quote.price`로 모의 체결. 가격의 `price_observed_at`과 주문의 `executed_at`을 따로 저장 | 나중에 생성된 신호로 이전 종가 체결을 가정해도 실제 실행 가능한 전략 검증이 되는 것은 아니다. |
| 체결 보존 | 견적·수량·비용·환율·현금 상태의 승인 확인, 원자적 저장과 동일 요청 재처리 방지 | 주문·현금·포지션·비용·환전 이력은 함께 처리된다. |

근거 코드: [계정 초기화](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/paper/accounts.py), [가격](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/paper/prices.py), [견적·주문 API](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/paper/router.py), [주문 처리](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/paper/service.py), [통합 정산·평가](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/paper/investment.py), [사용자 주문 흐름](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/frontend/src/app/paper-trading/page.tsx).

## 3. 비용과 환전

다음 숫자는 **해당 커밋의 시뮬레이션 설정값**이다. 실제 투자자의 적용 세율·증권사 요율을 확인한 표가 아니다.

| 항목 | 코드에 고정된 가정 |
| --- | --- |
| 정책 버전 | `sim-costs-2026-10-15-v1`, 적용기간 2026-01-01~2026-12-31. 지원하지 않는 날짜·분류는 거래 거부 |
| 미국 주식·ETF 수수료 | 매수·매도 0 bps. 규제 비용은 별도 |
| 한국 주식·ETF 수수료 | 매수·매도 1.5 bps = 0.015% |
| 한국 주식 매도 세금 가정 | KOSPI: 0.05% + 0.15%, KOSDAQ: 0.20%. ETF에는 이 거래세를 적용하지 않음 |
| 미국 매도 규제 비용 가정 | SEC: 4/4 이후 거래대금의 0.0000206, 그 전 0. TAF: 9/30까지 주당 USD 0.000195·최대 USD 9.79, 10~12월 0 |
| 환전 | 결제 통화 현금을 먼저 사용하고 부족한 매수 자금만 전환. 전환할 때 10 bps = 0.10% 스프레드 |
| 반올림 | 미국 비용은 센트 단위 올림, 한국 비용은 원 단위 내림. 환전 출금 올림·입금 내림 |
| 환율 | 현행 정책은 exchangerate.dev Free 지연 피드를 우선하고 검증된 FRED를 대체 소스로 사용. 실제 선택 공급자·관측/수집 시각을 기록 |
| 기록 | 견적 시 비용 정책·해시와 환율 고정, 승인 시 재검증. 주문 당시 환율·실제 환전·비용을 이후 평가 환율과 구분 |
| 반영하지 않는 항목 | 추가 슬리피지·호가/체결 대기열·시장충격 모델 미확인. 계정 배당 입금, 개인 양도/배당 과세, 일부 상품·거래소 비용은 모델링하지 않음 |

근거: [비용 설정 JSON](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/paper/cost_rules.json), [비용 계산](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/paper/costs.py), [환전·정산](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/paper/investment.py), [실행 환율·성과 분해 문서](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/docs/execution-fx-attribution.md).

비용은 이미 현금·취득원가·매도대금에 반영된다. 성과 계산에서 다시 일괄 차감하지 않는다. “비용을 반영한다”와 “실거래 비용을 모두 재현한다”는 구분한다.

## 4. 비교전략·수익률·최대낙폭

| 항목 | 코드·산출물 확인 결과 | 발표 가능 범위 |
| --- | --- | --- |
| 통합 평가 | 미국 현금·포지션 + 한국 현금·포지션의 현재 검증 환율 환산값 | USD 기준 통합 계정 평가 기능은 설명 가능 |
| 계정 누적 수익률 | `total_return_pct = (portfolio_value - initial_capital) / initial_capital * 100` | 비용 반영된 계정 평가값 기준 수익률 계산 기능. 실제 숫자는 미확인 |
| 실제 성과 이력 | 계정 생성 이후 실제 조회·평가 시점의 값을 저장. 과거로 소급 생성하지 않음. 통합 API는 최근 최대 500개 반환 | 매일 종가 전체 이력·독립 실전 성과가 확보됐다는 뜻은 아님 |
| 성과 그래프 | 유효 관측의 서로 다른 UTC 날짜·시각·평가값이 각각 2개 이상일 때 표시 | 같은 날 여러 번 주문/새로고침한 결과로 다일 성과 그래프를 만들지 않음 |
| 실제 수익률 숫자·기간 | 공개 추적 파일에 계정 DB·다일 통합 평가·수익률 보고서 없음 | **확인 필요. 수익률 수치와 전략 우위 제시 보류** |
| 최대낙폭 MDD | 확인한 계정 평가 API·성과 화면에 MDD 계산/표시를 찾지 못함. 완전한 일별 계정 평가 원본도 미제공 | **확인 필요. 0%로 기입하거나 하락분위수로 대체하지 않음** |
| 전략 비교 | Risk Score 자동 전략 대 매수보유의 동일 기간·자산·비용 비교 산출물 미확인 | 매수보유는 향후 검증 설계 제안으로만 표시 |
| 시장·업종 비교 정보 | SPY·KOSPI200은 시장 맥락, 검토된 업종 ETF는 조건부 과거 분석의 대용 지표 | 계정 수익률을 이긴 비교전략 실험으로 해석하지 않음 |

근거: [통합 평가·수익률 API 코드](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/paper/investment.py), [성과 화면](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/frontend/src/app/paper-trading/PortfolioWorkspace.tsx), [기존 로컬 검증 결과 보고](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/docs/real-stress-evidence-results.md).

기존 결과 보고서는 NVDA·SK하이닉스 등으로 조건부 분석과 수동 모의 주문 경로를 점검했다고 기록한다. 개인 DB, 상세 수치와 브라우저 증거는 Git 제외 경로에 있으며 이번에는 제공되지 않았다. 이 보고서는 계정 다일 수익률·MDD 또는 현재 AWS 배포 성공의 근거가 아니다.

향후 MDD를 계산하려면 같은 통화·비용 기준의 **전체 평가기간 일별 자산곡선**을 확보한다. 양수 크기로 보고할 때 `MDD = max_t(1 - V_t / max_{s<=t} V_s) * 100`이다. 이는 검증 설계이며 현재 구현·실측 결과가 아니다. 자금 유출입·누락일·평가시간 정책도 함께 정하고, API 최근 500개 조회만으로 전체 기간 MDD라고 단정하지 않는다.

## 5. 조건부 10D 분석과 실제 계정 성과의 구분

현재 스트레스와 비슷한 과거 OOS 구간을 고른 뒤, 보유 종목 또는 검토된 업종 대용 지표의 **이후 10거래일 조정종가 수익률 분포**를 보여주는 별도 분석이 있다. 사건 선택 뒤 비중첩 구간을 쓰며, 최소 20개 표본에서 중앙값·Q25~Q75·음의 수익률 빈도를, 100개에서 하방 Q10을 제공한다.

이 분석은 현재 보유 비중·현재 환율 고정·현금 수익 0·미래 매매 및 추가 비용 없음의 시나리오다. 실제 계정 성과, 미래 수익 예측, MDD가 아니다. 실제 모의 계정의 배당 현금 미반영과 달리 이 과거 분석은 배당·분할 조정 이력을 사용한다.

보유 종목의 공통 사건 표본과 검증된 이력이 필요하다. 미지원 종목·표본 부족·오래된 시장 상태에서는 결과를 보류한다. 미국·한국 동시 보유 시 두 시장을 합친 전망 범위도 보류한다. 확인한 공개 트리에는 필요한 비공개 `data/paper/stress-evidence/` 원본이 없으므로 양의 경로 수치 재현은 확인 필요다.

근거: [조건부 분석 코드](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/paper/stress_analytics.py), [방법론 문서](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/docs/conditional-portfolio-analytics.md).

## 6. Live Monitoring Log·Data Health의 구현과 남은 확인

WIP의 불변 로그·스냅샷 공개·조회 API와 Data Health 코드는 확인했다. 그러나 계획 문서의 데이터 계약과 완전히 같지는 않다.

| 계획 항목 | 확인한 WIP 구현 | 남은 확인 |
| --- | --- | --- |
| 생성 시각 | `generated_at`은 게시 트랜잭션 시각, 실제 추론은 별도 `model_inference_at` | 발표에서 계산 시각과 게시 시각을 합치지 않기 |
| 관측일·점수·MSI | `observation_date`, `risk_score`, `msi` 저장 | 실제 운영 행과 API/화면 값 대조 |
| 모델 식별 | `model_sha256` 저장 | 실제 배포 모델 파일과 대조 |
| 입력 식별 | `input_snapshot_sha256`은 **게시 payload JSON**의 해시. `source_history_sha256` 별도 | 계획의 정규화된 추론 feature row 해시와 동일하다고 주장하지 않기. 보관된 모델·입력 재현 확인 |
| 신선도 | 소스별 날짜, `data_status`, `data_freshness_status`, 스케줄 상태 | 지연·오류·재시작 사례의 실제 운영 확인 |
| 기록 유형 | 실제 코드는 `LIVE` / `RETROSPECTIVE`. LIVE는 진행 중인 검증된 추론 작업에서만 생성 | 계획의 SHADOW/BACKFILL은 개념 구분. 해당 이름의 enum 구현을 주장하지 않기 |
| 보존·게시 | UPDATE/DELETE/중복 대체 방지 트리거와 게시 트랜잭션 연결, 읽기 API | 재배포 후 지속성·외부 전달 증거 확인. 스냅샷 게시가 사용자 수신을 입증하지는 않음 |
| Data Health | `CURRENT` / `DELAYED` / `STALE` / `PARTIAL` / `ERROR` | 계획의 FRESH 등 명칭과 구분하고 실제 화면으로 설명 |

근거: [불변 모니터링 로그](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/operations/monitoring.py), [스냅샷 게시](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/operations/store.py), [Data Health](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/operations/service.py), [로그 조회 API](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/src/api/monitoring.py).

[10/14 수동 갱신 보고서](https://github.com/tina77302/market-stress-early-warning/blob/4a75acd1e1e73e58c9cb600519401a9ca4a22bc1/docs/data-reliability-live-verification.md)는 실제 공급자 갱신을 보고하지만 당시 운영 스케줄러는 실행 중이 아니었다고 명시한다. 이 자료로 무인 운영 지속성이나 수개월의 prospective OOS 성과를 주장하지 않는다. 현재 AWS 배포 커밋·재시작·로그 보존 증거는 이번 작업에서 확인하지 않았다.

## 7. 기존 모델 성능표의 불일치

기존 main README는 미국 10D OOS 5,060개와 성능표를 제시한다. 현재 추적된 `data/processed/oos_predictions.csv`는 **5,057행, 2006-08-09~2026-09-16**이며 계정 가치·거래 이력 데이터가 아니다. 두 자료의 표본이 같다고 검증되지 않았다. 본 발표안의 성능표는 기존 README의 인용으로만 남기며 **원본 정합성 확인 전 발표 확정 수치로 사용하지 않는다**. 이번 작업에서 모델 재학습·임계값 조정·성과 재산출을 진행하지 않았다.

## 8. 발표 전 남은 증거

- [ ] 시연 커밋이 WIP 구현을 포함하는지 확인하고 화면·모델·데이터 시점을 기록한다.
- [ ] 실제 계정 생성일, 주문 원장, 비용·환율, 전체 평가 이력을 익명화하여 대조한다.
- [ ] 수익률과 MDD를 발표하려면 동일 기간·자산·비용의 원본 및 비교전략 결과를 확보한다. 없으면 수치 보류를 유지한다.
- [ ] WATCH D3 원본 정의·19개 사례 표를 연결한다. 현재 수치는 사용자 확정 연구 결론이며 새로 재현하지 않았다.
- [ ] Live 로그의 게시/추론 시각·해시 의미·재시작 보존과 배포 기록을 대조한다.
- [ ] 기존 OOS 표본 수 5,060/5,057 차이를 해소한 원본 표를 팀원이 확정한다.
- [ ] 두 발표자가 6분/4분으로 합동 리허설한다.
