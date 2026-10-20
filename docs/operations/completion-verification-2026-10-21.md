# 제품 완성 작업 결과 — 2026-10-21 (Asia/Seoul)

## 상태

**소스 보완 및 제한된 검증 완료. AWS 배포·최종 UI·전체 QA는 미완료.**

기준 구현: `d0795784307a4c73a0a79ce1b20d80a715e53b6a` (wip/data-automation).
최종 결정·기존 발표 자료는 문서 브랜치에서 가져와 같은 변경에 포함했다.
모델 학습, WATCH 튜닝, 타깃·MSI·입력변수 변경은 수행하지 않았다.

## 실제 수행

- 기존 Live Monitoring Log와 Data Health 구현 및 테스트 확인.
- 추론 입력의 관측일·컬럼 순서·자료형·값을 고정 JSON으로 보관하고 `input_hash` 산출.
- 실제 추론 모델 바이트도 실행 산출물 디렉터리에 해시 기반 파일명으로 보관.
- 기존 `input_snapshot_sha256`는 게시 payload 해시로 그대로 유지. 새 입력 해시와 혼동하지 않음.
- 같은 job의 같은 게시 요청 재시도는 원래 snapshot ID 반환. 바뀐 payload/기록 유형의 재시도는 거절.
- receipt와 원래 로그·snapshot·포인터·job 상태는 동일 SQLite 트랜잭션으로 저장.
- 기존 행·과거 산출물은 소급 변경하지 않음. 이전 로그의 새 입력 해시는 null.
- 최종 연구 종료 결정 및 팀원/김주미 발표 역할 문서를 구현 변경과 함께 정리.

## 이번에 실행한 검증

| 검증 | 결과와 한계 |
| --- | --- |
| 입력·모델 보존, 반복 저장, 입력 변경, 원본 변조, 비정상 입력 | unittest 2개 통과 |
| 기존 로그 불변성·LIVE 요건·snapshot 트랜잭션 롤백·신규 재시도 검증 | 27개 통과, HTTP TestClient 사용 4개 제외 |
| 변경 Python 파일 문법 검사 | 통과 |
| 전체 소스 compileall | 기존 미수정 파일 src/models/early_warning_evaluation.py 358행 IndentationError 발견 |
| 전체 pytest | Windows에서 fcntl 없음으로 conftest 수집 차단 |
| 원래 로그 테스트 직접 실행 | exchange_calendars 미설치 |
| 제한된 로그 테스트 실행 방식 | 달력은 기존 테스트의 고정 expected fixture를 사용. import만 허용하는 빈 exchange_calendars 모듈을 테스트 프로세스 안에 주입. 실거래일 달력이나 운영 설치 검증 아님 |
| HTTP TestClient 검사 | 실행 중 응답 대기에서 멈춰 중단. 통과로 계산하지 않음 |
| Docker | Linux Engine pipe 없음. 이미지 빌드·컨테이너 실행 불가 |
| 배포 사이트 UI | 브라우저 연결 타임아웃. 이번 화면/버튼 QA 미수행 |
| 배포 API | 외부 읽기 도구로 접근 실패. 운영 로그 행/소스 신선도 확인 불가 |
| AWS | 사용 가능한 원격 실행 대상 확인 안 됨. 배포·재시작·롤백 미수행 |

27개 로그 테스트는 임시 SQLite와 fixture만 사용했다. 실제 LIVE 행을 생성하거나 과거 자료를 실시간 실적으로 등록하지 않았다. 모델 원본으로 실제 점수를 재현하는 통합 테스트는 아직 수행하지 못했다.

## 남은 완료 조건

1. Linux 운영 의존성 환경에서 테스트 전체 실행. 달력 fixture 대체 없이 실제 달력·HTTP 테스트 통과 필요.
2. 현재 고정 모델로 worker 실행 후 input JSON, model 파일 해시 및 점수 재현 확인.
3. 모델 학습 종료일·등록일 provenance를 확보. 이 변경만으로 prospective OOS 적격성을 인증하지 않음.
4. 고정 릴리스로 [AWS 배포 절차](../aws-staging-release.md) 수행. 승인된 기존 artifact bundle·EBS·외부 환경설정 사용.
5. 새 증거 파일이 EBS의 operations staging 디렉터리에 남고 백업/복구·재시작 후 동일한지 확인.
6. 실제 한국·미국 로그/소스별 Data Health/두 언어/모의투자 주문 복원·금액 표시 QA 수행.
7. 10거래일 정답이 성숙한 후 사전 지정 기준으로 평가. 로그 구축 자체를 실전 성능으로 발표하지 않음.

모델 파일을 실행별로 보관하므로 저장량이 증가한다. 로그와 연결된 증거를 임의로 지우지 말고 보관 정책을 확정해야 한다. 기존 학습 연구 파일의 구문 결함은 이번 범위에서 수정하거나 실행하지 않았다.
