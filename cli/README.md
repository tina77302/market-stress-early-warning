# cli/

`.env` 에 저장된 API 키를 적용해 한국 시장 데이터 수집 스크립트(`src/korea/`)를 터미널에서 실행하는 셸 스크립트 모음입니다.

| 파일 | 역할 |
|------|------|
| `fetch_korea_data.sh` | `.env` 키를 적용해 수집 스크립트를 1회 실행 |
| `batch_fetch_korea_data.sh` | 위 스크립트를 배치로 실행하고 결과를 `reports/fetch_report.md` 에 기록 |
| `schedule_batch.sh` | 배치를 30분 단위 cron 에 등록 / 해제 / 상태 확인 |
| `logs/` | 실행별 전체 출력 로그 (자동 생성, git 제외) |
| `reports/fetch_report.md` | 30분마다 추가되는 수집 결과 리포트 (자동 생성, git 제외) |

## 🚀 처음 실행하는 순서 (여기부터 읽으세요)

`cli/` 에는 셸 스크립트가 3개 있지만, **사용자가 직접 실행하는 것은 `fetch_korea_data.sh` 와 `schedule_batch.sh` 두 개**입니다.
`batch_fetch_korea_data.sh` 는 cron 이 호출하는 내부용 래퍼라서 평소에는 직접 실행할 일이 없습니다.

| 순서 | 실행할 것 | 목적 | 소요 |
|:---:|-----------|------|------|
| 0 | (sh 아님) `.venv` 생성 + `pip install`, `.env` 에 키 입력 | 실행 환경 준비. 아래 [사전 준비](#사전-준비) 1~8 단계 | 5분 |
| **1** | **`cli/fetch_korea_data.sh test-vkospi`** | **최초 실행 스크립트.** `.env` 키와 Python 환경이 맞는지 API 1회 호출로 확인 | 수 초 |
| 2 | `cli/fetch_korea_data.sh all` | 2010년부터 전체 데이터 1회 수집 (`data/raw/korea/*.csv` 생성) | 30분~1시간 |
| 3 | `cli/schedule_batch.sh install` | 이후 30분마다 자동 수집하도록 cron 등록 | 수 초 |
| 4 | `cli/schedule_batch.sh status` | cron 등록 확인, 최근 실행 결과 보기 | 수 초 |

```bash
# 0. 환경 준비 (최초 1회)
cd /path/to/market-stress-early-warning
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt       # 또는: pandas requests python-dotenv 만
cp .env.example .env && vi .env                 # KRX_API_KEY, ECOS_API_KEY 입력

# 1. ★ 최초 실행: 키 / 환경 점검
cli/fetch_korea_data.sh test-vkospi
#    → "[INFO] KRX_API_KEY set (40 chars)" 와 "HTTP Status: 200" 이 보이면 OK

# 2. 전체 데이터 1회 수집 (오래 걸림, 끊겨도 다시 실행하면 이어받음)
cli/fetch_korea_data.sh all

# 3. 30분 주기 자동 수집 등록
cli/schedule_batch.sh install

# 4. 확인
cli/schedule_batch.sh status
cat cli/reports/fetch_report.md
```

**왜 이 순서인가**

- 1단계를 건너뛰고 2·3단계로 가면, 키 오류나 패키지 누락이 30분마다 리포트에 ❌ FAIL 로만 쌓입니다. 먼저 `test-*` 로 한 번 확인하는 것이 빠릅니다.
- 2단계를 건너뛰고 바로 3단계(cron)만 등록해도 동작은 합니다. 다만 첫 cron 실행이 전체 다운로드를 맡게 되어 30분~1시간 동안 돌고, 그 사이 돌아오는 주기는 리포트에 ⏭️ SKIPPED 로 기록됩니다. 터미널에서 진행 상황을 직접 보려면 2단계를 먼저 하세요.
- 3단계 이후에는 아무것도 직접 실행하지 않아도 됩니다. 결과는 `cli/reports/fetch_report.md` 에 30분마다 쌓입니다.

**스크립트 간 호출 관계**

```
cron (30분마다)
 └─ schedule_batch.sh install 로 등록된 crontab 항목
     └─ batch_fetch_korea_data.sh          ← 내부용. 로그 저장 + 리포트 append
         └─ fetch_korea_data.sh <command>  ← 실제 수집. 사용자가 1회 실행할 때도 이것
             └─ .venv/bin/python src/korea/download_*.py
```

> 각 스크립트의 자세한 옵션은 아래 절을 참고하세요: [fetch_korea_data.sh](#fetch_korea_datash) · [30분 단위 배치 수집](#30분-단위-배치-수집-batch_fetch_korea_datash--schedule_batchsh)

## 🔑 `.env` 키 5개의 쓰임새

현재 `.env` 에는 아래 5개의 키가 있습니다. **이 중 `cli/` 스크립트가 실제로 사용하는 것은 `KRX_API_KEY` 와 `ECOS_API_KEY` 두 개뿐**입니다. 나머지 3개는 cli 와 무관하거나 아직 코드에서 참조되지 않습니다. (값은 적지 않습니다. `.env` 는 git 에 올리지 마세요.)

| 키 | cli 사용 | 사용하는 코드 | 용도 | 상태 (2026-10-16 확인) |
|----|:---:|---------------|------|------|
| `KRX_API_KEY` | ✅ | `src/korea/download_krx_indices.py`<br>`src/korea/download_vkospi.py`<br>`src/korea/test_krx_api.py`<br>`src/korea/test_vkospi_api.py` | KRX Open API (`data-dbg.krx.co.kr/svc/apis/idx/...`) 호출. HTTP 헤더 `AUTH_KEY` 로 전달. KOSPI / KOSPI200 일별 지수와 VKOSPI 수집 | ✅ 동작 확인. `kospi_dd_trd`, `drvprod_dd_trd` 두 엔드포인트 모두 HTTP 200 |
| `ECOS_API_KEY` | ✅ | `src/korea/download_ecos_credit.py`<br>`src/korea/test_ecos_credit.py` | 한국은행 ECOS `StatisticSearch` API 호출. URL 경로에 키 포함. 통계표 `817Y002`(시장금리, 일별)에서 국고채 3년(`010200000`), 회사채 AA- 민평 3년(`010310000`) 수집 | ✅ 동작 확인. 2010-01-04 ~ 2026-10-02 전 구간 약 4,140 행 반환. 단, 간헐적으로 `INFO-200 해당하는 데이터가 없습니다` 가 돌아오는 경우가 관측됨 (아래 참고) |
| `FRED_API_KEY` | ❌ | `src/config.py` (읽기만 함)<br>`docker-compose.yml` (api 컨테이너에 전달) | 미국 FRED 데이터용으로 준비된 키. 그러나 실제 FRED 수집 코드 `src/data/fetcher.py` 는 키가 필요 없는 공개 CSV 엔드포인트(`fred.stlouisfed.org/graph/fredgraph.csv`)를 사용하며, `config.FRED_API_KEY` 를 import 하는 모듈이 없음 | ⚪ 정의만 되어 있고 **실제로 사용되지 않음**. 비워 두어도 파이프라인 동작에 영향 없음 |
| `EXCHANGERATE_API_KEY` | ❌ | (없음) | 환율 API 용으로 추정되나 저장소 어디에서도 참조되지 않음 (`*.py`, `*.ts`, `*.tsx`, `*.js`, `*.sh`, `*.yml`, `*.json` 전체 검색) | ⚪ **미사용**. 향후 환율 수집 기능을 위해 미리 넣어 둔 것으로 보임 |
| `PAPER_SESSION_SECRET` | ❌ | (없음) | `.env` 주석에 "Private paper-workspace session hashing secret" 으로 기재. 세션 해싱용 비밀값이지만 저장소 코드에서 참조하는 곳이 없음 | ⚪ **미사용**. 다른 저장소나 아직 커밋되지 않은 기능용으로 추정 |

### 키별 동작 확인 방법

```bash
cli/fetch_korea_data.sh test-krx       # KRX_API_KEY  → KOSPI / KOSPI200 1일치
cli/fetch_korea_data.sh test-vkospi    # KRX_API_KEY  → VKOSPI 1일치
cli/fetch_korea_data.sh test-ecos      # ECOS_API_KEY → 국고채 / 회사채 최근 2주치
cli/fetch_korea_data.sh test           # 위 세 가지 모두
```

스크립트는 명령에 필요한 키만 검사합니다. `FRED_API_KEY`, `EXCHANGERATE_API_KEY`, `PAPER_SESSION_SECRET` 은 cli 실행에 전혀 쓰이지 않으므로 비어 있어도 됩니다.

### ECOS `INFO-200` 참고

ECOS 는 HTTP 200 과 함께 본문에 `{"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}` 를 돌려주는 경우가 있습니다. 같은 URL 을 바로 다시 호출하면 정상 데이터가 오는 것으로 보아 ECOS 쪽의 일시적 응답으로 판단됩니다.

- `download_ecos_credit.py` 는 이 응답을 `RuntimeError` 로 처리하며, 재시도 루프가 `requests.RequestException` 만 잡기 때문에 **INFO-200 이 오면 재시도 없이 실패**합니다.
- 30분 배치에서 `ecos` 가 ❌ FAIL 로 기록되고 로그에 `ECOS API Error: INFO-200` 이 보이면 키 문제가 아니라 이 경우입니다. 다음 주기에 다시 성공하면 정상입니다.
- 계속 실패한다면 `.env` 의 키가 만료되었거나(ECOS 키는 발급 후 미사용 시 만료될 수 있음) 일일 호출 한도를 넘긴 것입니다. `test-ecos` 로 확인하세요.

## fetch_korea_data.sh

KRX(한국거래소) Open API 와 ECOS(한국은행 경제통계) API 에서 데이터를 받아 `data/raw/korea/` 아래 CSV 로 저장합니다.

### 사전 준비

이 스크립트는 **Python 가상환경(venv)** 안에서 실행하는 것을 전제로 합니다.
아래 순서대로 한 번만 구성하면 이후에는 `cli/fetch_korea_data.sh <command>` 만 실행하면 됩니다.

#### 1. Python 버전 확인

Python **3.10 이상**이 필요합니다. (개발 환경: Ubuntu 24.04 / WSL2, Python 3.12.3)

```bash
python3 --version
# Python 3.12.3
```

`python3` 가 없거나 버전이 낮으면 설치합니다.

```bash
# Ubuntu / Debian / WSL2
sudo apt update
sudo apt install -y python3 python3-pip

# macOS (Homebrew)
brew install python@3.12
```

#### 2. venv 모듈 확인 (Ubuntu / WSL2 전용)

Ubuntu 계열은 `venv` 모듈이 별도 패키지로 분리되어 있어 아래 오류가 날 수 있습니다.

```
The virtual environment was not created successfully because ensurepip is not available.
```

이 경우 Python 버전에 맞는 venv 패키지를 설치합니다.

```bash
sudo apt install -y python3-venv          # 기본 Python 버전용
# 또는 버전을 명시
sudo apt install -y python3.12-venv
```

설치 여부 확인:

```bash
dpkg -l | grep python3.*-venv
# ii  python3.12-venv  3.12.3-...
```

#### 3. 가상환경 생성

**반드시 프로젝트 루트에서** 실행합니다. 스크립트가 `<프로젝트 루트>/.venv/bin/python` 을 자동으로 찾기 때문입니다.

```bash
cd /path/to/market-stress-early-warning
python3 -m venv .venv
```

생성이 끝나면 다음 구조가 만들어집니다.

```
.venv/
├── bin/
│   ├── activate          # 활성화 스크립트 (bash / zsh)
│   ├── activate.fish     # fish shell 용
│   ├── pip
│   ├── python -> python3
│   └── python3 -> /usr/bin/python3.12
├── lib/python3.12/site-packages/
└── pyvenv.cfg
```

`.venv/` 는 이미 `.gitignore` 에 등록되어 있어 커밋되지 않습니다.

#### 4. 가상환경 활성화

```bash
# bash / zsh
source .venv/bin/activate

# fish
source .venv/bin/activate.fish

# Windows PowerShell (WSL 이 아닌 네이티브 Windows 에서 실행할 경우)
.venv\Scripts\Activate.ps1
```

활성화되면 프롬프트 앞에 `(.venv)` 가 붙습니다. 아래 명령으로 올바른 Python 이 선택됐는지 확인합니다.

```bash
which python
# /path/to/market-stress-early-warning/.venv/bin/python

python --version
# Python 3.12.3
```

> **참고**: `fetch_korea_data.sh` 는 `.venv/bin/python` 을 절대경로로 직접 호출하므로
> 활성화하지 않아도 동작합니다. 활성화는 `pip install` 을 편하게 하기 위한 단계입니다.

#### 5. pip 업그레이드 및 패키지 설치

```bash
# pip 최신화 (오래된 pip 는 일부 wheel 설치에 실패할 수 있음)
python -m pip install --upgrade pip

# 프로젝트 전체 의존성 설치 (모델 학습 / API 서버 포함)
pip install -r requirements.txt
```

데이터 수집 스크립트만 쓸 경우 아래 세 패키지만 있어도 됩니다.

```bash
pip install pandas requests python-dotenv
```

> `requirements.txt` 전체 설치는 xgboost, shap, matplotlib 등을 포함해 수 분이 걸릴 수 있습니다.
> 네트워크가 느리면 먼저 최소 패키지로 시작하고, 모델 학습이 필요할 때 전체 설치를 하세요.

#### 6. 설치 확인

```bash
python -c "import pandas, requests, dotenv; print('OK', pandas.__version__)"
# OK 2.x.x  (또는 3.x.x)
```

`ModuleNotFoundError` 가 나면 5 단계로 돌아가 설치를 다시 확인합니다.
스크립트도 실행 시 같은 검사를 하며, 실패하면 아래 메시지와 함께 종료합니다.

```
[ERROR] python 패키지가 부족합니다 (/path/.venv/bin/python). 다음을 실행하세요: /path/.venv/bin/python -m pip install -r requirements.txt
```

#### 7. 가상환경 비활성화 / 삭제

```bash
deactivate            # 현재 셸에서 가상환경 해제

rm -rf .venv          # 완전히 삭제 후 3 단계부터 다시 만들 때
```

#### 8. `.env` 파일 생성 및 API 키 설정

프로젝트 루트에 `.env` 파일을 만들고 API 키를 넣습니다.

```bash
cp .env.example .env
```

`.env` 를 열어 아래 두 줄을 추가하거나 값을 채웁니다.

```dotenv
KRX_API_KEY=발급받은_KRX_키
ECOS_API_KEY=발급받은_ECOS_키
```

- KRX 키: https://openapi.krx.co.kr (지수 → "KOSPI 시리즈 일별시세정보", "파생상품지수 일별시세정보" 서비스 신청 필요)
- ECOS 키: https://ecos.bok.or.kr/api (인증키 신청)

`.env` 는 `.gitignore` 에 등록되어 있어 커밋되지 않습니다. 키 값을 저장소에 올리지 마세요.

#### 9. 동작 확인

가상환경 구성과 키 설정이 끝났으면 단일 날짜 테스트로 전체 경로를 확인합니다.

```bash
cli/fetch_korea_data.sh test-vkospi
```

아래처럼 `[INFO]` 세 줄이 나오고 HTTP 200 응답이 보이면 준비 완료입니다.

```
[INFO] env loaded: /path/to/market-stress-early-warning/.env
[INFO] python: /path/to/market-stress-early-warning/.venv/bin/python
[INFO] KRX_API_KEY set (40 chars)

============================================================
RUN test_vkospi_api.py
============================================================
...
HTTP Status: 200
받은 지수 개수: 322
```

#### Python 선택 우선순위

스크립트는 아래 순서로 Python 을 찾습니다. 다른 위치의 가상환경을 쓰려면 `PYTHON=` 으로 직접 지정합니다.

| 순서 | 경로                                  | 비고                               |
|------|---------------------------------------|------------------------------------|
| 1    | `$PYTHON` 환경변수                    | 지정된 경우 최우선                 |
| 2    | `<프로젝트 루트>/.venv/bin/python`    | 권장 위치                          |
| 3    | `<프로젝트 루트>/venv/bin/python`     | 기존 관례 호환                     |
| 4    | `python3` (PATH)                      | 시스템 Python, 패키지가 없으면 실패 |

```bash
# 예: conda 환경이나 다른 경로의 venv 사용
PYTHON=~/miniconda3/envs/mkt/bin/python cli/fetch_korea_data.sh vkospi
```

### 사용법

```bash
cli/fetch_korea_data.sh <command>
```

| command       | 설명                                   | 출력 파일                           |
|---------------|----------------------------------------|-------------------------------------|
| `krx`         | KOSPI / KOSPI200 일별 지수 수집        | `data/raw/korea/krx_indices.csv`    |
| `vkospi`      | VKOSPI(코스피 200 변동성지수) 수집     | `data/raw/korea/vkospi.csv`         |
| `ecos`        | ECOS 금리 / 신용 스프레드 시계열 수집  | `data/raw/korea/ecos_credit.csv`    |
| `all`         | `krx` → `vkospi` → `ecos` 순서로 실행  | 위 세 파일                          |
| `test-krx`    | KRX 지수 API 단일 날짜 호출 테스트     | 없음 (화면 출력)                    |
| `test-vkospi` | VKOSPI API 단일 날짜 호출 테스트       | 없음 (화면 출력)                    |
| `test-ecos`   | ECOS API 호출 테스트                   | 없음 (화면 출력)                    |
| `test`        | 위 세 가지 테스트 모두 실행            | 없음 (화면 출력)                    |
| `--help`      | 도움말 출력                            |                                     |

### 예시

```bash
# 키가 제대로 설정됐는지 먼저 확인
cli/fetch_korea_data.sh test-vkospi

# VKOSPI 전체 기간 다운로드
cli/fetch_korea_data.sh vkospi

# 세 가지 데이터 모두 수집
cli/fetch_korea_data.sh all

# 다른 env 파일 / 다른 Python 사용
ENV_FILE=/path/to/other.env cli/fetch_korea_data.sh krx
PYTHON=/path/to/python cli/fetch_korea_data.sh ecos
```

정상 실행 시 출력 예:

```
[INFO] env loaded: /home/ubuntu/market-stress-early-warning/.env
[INFO] python: /home/ubuntu/market-stress-early-warning/.venv/bin/python
[INFO] KRX_API_KEY set (40 chars)

============================================================
RUN download_vkospi.py
============================================================
...
```

### 환경변수

| 변수       | 기본값                              | 설명                                 |
|------------|-------------------------------------|--------------------------------------|
| `ENV_FILE` | `<프로젝트 루트>/.env`              | 읽어올 env 파일 경로                 |
| `PYTHON`   | `.venv` / `venv` / `python3` 자동   | 사용할 Python 실행 파일              |

### 동작 방식

1. `.env` 를 `source` 해서 셸 환경변수로 export 합니다. (각 `.py` 도 내부에서 `load_dotenv()` 를 호출하므로 둘 중 하나만 있어도 동작합니다.)
2. 명령에 필요한 키(`KRX_API_KEY` 또는 `ECOS_API_KEY`)가 비어 있으면 즉시 종료합니다. 키 값은 출력하지 않고 길이만 표시합니다.
3. 스크립트 내부 상대경로(`data/raw/korea/...`)가 맞도록 프로젝트 루트로 이동한 뒤 `src/korea/<script>.py` 를 실행합니다.

### 수집 스크립트 특징

- **이어받기**: 출력 CSV 가 이미 있으면 마지막 날짜 다음 날부터 재개합니다. 단, 기존 파일 시작일이 목표 시작일(2010-01-04)보다 늦으면 부분 파일로 보고 처음부터 다시 받습니다.
- **체크포인트**: 100 요청마다 CSV 를 중간 저장하므로 중간에 끊겨도 다시 실행하면 이어집니다.
- **재시도**: 요청 실패 시 최대 5 회, 2초 / 4초 / 6초 ... 간격으로 재시도하고, 끝까지 실패한 날짜는 마지막에 목록으로 출력합니다.
- **소요 시간**: KRX 는 날짜별로 1 요청씩 보내므로 2010 년부터 전체 수집 시 약 4,400 요청, 요청당 0.2초 대기로 15 분 이상 걸립니다.

### 종료 코드

| 코드 | 의미                                                        |
|------|-------------------------------------------------------------|
| 0    | 정상 종료                                                   |
| 1    | 알 수 없는 command, `.env` 없음, 키 누락, Python/패키지 부족, 또는 `.py` 실행 실패 |

### 문제 해결

**가상환경 관련**

- `ensurepip is not available` → `sudo apt install -y python3.12-venv` 후 `rm -rf .venv` 하고 다시 생성합니다.
- `which python` 이 `/usr/bin/python3` 를 가리킴 → 가상환경이 활성화되지 않은 상태입니다. `source .venv/bin/activate` 를 실행하거나, 활성화 없이 `.venv/bin/pip install ...` 처럼 절대경로로 호출합니다.
- `.venv` 를 다른 경로에 만들었음 → 스크립트는 프로젝트 루트의 `.venv` / `venv` 만 자동 인식합니다. `PYTHON=/경로/bin/python cli/fetch_korea_data.sh ...` 로 지정하세요.
- 프로젝트 폴더를 옮긴 뒤 `bad interpreter` 오류 → venv 는 절대경로를 포함하므로 이동하면 깨집니다. `rm -rf .venv` 후 다시 만듭니다.
- `pip install` 중 `externally-managed-environment` 오류 → 시스템 Python 에 직접 설치하려 할 때 나옵니다. 가상환경을 활성화했는지 확인하세요.

**스크립트 실행 관련**

- `.env 파일이 없습니다` → `cp .env.example .env` 후 키를 채워 넣습니다.
- `KRX_API_KEY 가 ... 설정되어 있지 않습니다` → `.env` 에 해당 줄이 있는지, 값이 비어 있지 않은지 확인합니다.
- `python 패키지가 부족합니다` → 안내된 Python 으로 `pip install -r requirements.txt` 를 실행하거나 `PYTHON=` 으로 올바른 가상환경을 지정합니다.
- `HTTP 401/403` → 키가 만료됐거나 해당 API 서비스 신청이 승인되지 않은 경우입니다. `test-*` 명령으로 먼저 확인하세요.

---

## 30분 단위 배치 수집 (batch_fetch_korea_data.sh + schedule_batch.sh)

`fetch_korea_data.sh` 를 30분마다 자동 실행하고, 매 실행 결과를 마크다운 리포트에 로그처럼 쌓습니다.

### 구성 요소

```
cli/
├── fetch_korea_data.sh         # 1회 수집
├── batch_fetch_korea_data.sh   # 배치 래퍼: 수집 실행 + 로그 저장 + 리포트 append
├── schedule_batch.sh           # cron 등록 / 해제 / 상태 / 즉시 실행 / loop
├── logs/
│   ├── cron.log                            # cron 이 실행한 배치의 표준 출력 누적
│   ├── .batch.lock                         # 동시 실행 방지용 잠금 파일
│   └── 20261016_104500_vkospi.log          # 실행별 전체 출력 (명령 단위)
└── reports/
    ├── fetch_report.md                     # 30분마다 항목이 추가되는 리포트
    └── .state/<command>.rows               # 직전 실행의 행 수 (증가분 계산용)
```

### 빠른 시작

```bash
# 1. (최초 1회) 가상환경과 .env 가 준비되어 있는지 확인
cli/fetch_korea_data.sh test-vkospi

# 2. cron 에 30분 주기로 등록
cli/schedule_batch.sh install

# 3. 등록 상태 / 최근 실행 결과 확인
cli/schedule_batch.sh status

# 4. 리포트 보기
cat cli/reports/fetch_report.md
```

등록되는 crontab 항목 (매시 00분, 30분 실행):

```
*/30 * * * * cd /path/to/market-stress-early-warning && BATCH_COMMANDS="krx vkospi ecos" /path/to/cli/batch_fetch_korea_data.sh >> /path/to/cli/logs/cron.log 2>&1 # market-stress-korea-fetch
```

### schedule_batch.sh 명령

| command   | 설명 |
|-----------|------|
| `install` | crontab 에 30분 주기 항목 등록. 이미 있으면 갱신. cron 서비스가 꺼져 있으면 경고 출력 |
| `remove`  | crontab 에서 항목 제거 (`# market-stress-korea-fetch` 태그로 식별) |
| `status`  | cron 서비스 상태, crontab 항목, 리포트의 마지막 항목, `cron.log` 마지막 10줄 표시 |
| `run-now` | cron 과 같은 최소 환경(PATH 등)으로 배치를 즉시 1회 실행. cron 에서의 동작을 미리 확인할 때 사용 |
| `loop`    | cron 없이 포그라운드에서 30분마다 반복. WSL2 처럼 cron 이 꺼져 있는 환경용 |

환경변수:

| 변수             | 기본값             | 설명 |
|------------------|--------------------|------|
| `CRON_SCHEDULE`  | `*/30 * * * *`     | cron 표현식. 예: `0 * * * *` (매시 정각) |
| `BATCH_COMMANDS` | `krx vkospi ecos`  | 배치가 실행할 명령. crontab 줄에 함께 기록됨 |
| `LOOP_INTERVAL`  | `1800`             | `loop` 모드 간격(초) |

```bash
# 예: VKOSPI 만 매시 15분 / 45분에 수집
CRON_SCHEDULE="15,45 * * * *" BATCH_COMMANDS="vkospi" cli/schedule_batch.sh install

# cron 없이 백그라운드 반복 실행
nohup cli/schedule_batch.sh loop > cli/logs/loop.out 2>&1 &
```

### batch_fetch_korea_data.sh 동작

1. 인자(또는 `BATCH_COMMANDS`)로 받은 명령을 순서대로 `fetch_korea_data.sh <command>` 로 실행합니다.
2. 명령별 전체 출력을 `cli/logs/<YYYYMMDD_HHMMSS>_<command>.log` 에 저장합니다.
3. 실행 후 출력 CSV 의 행 수, 첫/마지막 날짜, 파일 크기를 읽고, `reports/.state/` 에 저장된 직전 행 수와 비교해 증가분을 계산합니다.
4. 로그에서 `[WARNING]` / `[ERROR]` 줄 수와 "실패한 날짜" 수를 집계합니다.
5. 결과를 `reports/fetch_report.md` 끝에 한 항목으로 추가합니다. 실패 시 로그 마지막 30줄을, 실패 날짜가 있으면 그 목록을 접이식 블록으로 함께 기록합니다.
6. `LOG_RETENTION_DAYS`(기본 14일)보다 오래된 로그 파일을 삭제합니다. `0` 이면 삭제하지 않습니다.

**동시 실행 방지**: `flock` 으로 `logs/.batch.lock` 을 잠급니다. 전체 수집은 15분 이상 걸리므로 이전 배치가 끝나기 전에 다음 30분 주기가 돌아오면, 그 실행은 아무 것도 하지 않고 리포트에 ⏭️ SKIPPED 로만 기록됩니다. 첫 전체 다운로드 직후 SKIPPED 가 몇 번 보이는 것은 정상입니다.

```bash
# 수동 실행 예
cli/batch_fetch_korea_data.sh                 # krx vkospi ecos
cli/batch_fetch_korea_data.sh vkospi          # 하나만
LOG_RETENTION_DAYS=30 cli/batch_fetch_korea_data.sh
```

### 리포트 형식 (reports/fetch_report.md)

실행마다 아래 형태의 항목이 시간순으로 추가됩니다.

```markdown
## 2026-10-16 10:45:00 — ✅ SUCCESS

- 실행 명령: `vkospi`
- 시작: 2026-10-16 10:45:00 / 종료: 2026-10-16 11:12:41 / 총 소요: 27m 41s
- 호스트: `DESKTOP-XXXX` / 실행자: `ubuntu`

| command | status | 소요 | 출력 파일 | 행 수 | 증가 | 날짜 범위 | 크기 | WARN / ERR / 실패날짜 | 로그 |
|---|---|---|---|---:|---:|---|---:|---|---|
| `vkospi` | ✅ SUCCESS | 27m 41s | `data/raw/korea/vkospi.csv` | 4123 | 4116 | 2010-01-04 → 2026-10-02 | 236K | 0 / 0 / 0 | [log](../logs/20261016_104500_vkospi.log) |

---
```

| 컬럼 | 의미 |
|------|------|
| status | ✅ SUCCESS (exit 0) / ❌ FAIL (exit N) / ⏭️ SKIPPED |
| 행 수 | 실행 후 CSV 데이터 행 수 (헤더 제외) |
| 증가 | 직전 배치 대비 늘어난 행 수. 음수면 파일이 다시 받아졌거나 줄어든 것 |
| 날짜 범위 | CSV 첫 행과 마지막 행의 Date |
| WARN / ERR / 실패날짜 | 로그 내 `[WARNING]` 줄 수 / `[ERROR]` 줄 수 / 5회 재시도 후에도 실패한 날짜 수 |
| 로그 | 해당 실행의 전체 출력 파일 |

실패(❌)한 명령은 표 아래에 로그 마지막 30줄이, 실패 날짜가 있는 명령은 날짜 목록이 `<details>` 접이식 블록으로 붙습니다.

### 주의 사항

- **수집 종료일이 고정되어 있습니다.** `src/korea/download_*.py` 의 `END_DATE` 가 `2026-10-02` 로 하드코딩되어 있어, 전체 다운로드가 끝난 뒤의 30분 배치는 "already up to date" 로 끝나고 새 데이터를 받지 않습니다. 이후 날짜를 계속 받으려면 각 스크립트의 `END_DATE` 를 `datetime.today()` 등으로 바꿔야 합니다.
- **첫 실행은 오래 걸립니다.** krx / vkospi 각각 약 4,400 요청(15분 이상), ecos 는 시리즈별 수 회 요청입니다. 그동안 돌아오는 30분 주기는 SKIPPED 로 기록됩니다.
- **cron 은 PATH 가 최소입니다.** 배치는 프로젝트 루트의 `.venv/bin/python` 을 절대경로로 찾으므로 `.venv` 가 있어야 합니다. 다른 Python 을 쓰려면 crontab 줄에 `PYTHON=/path/bin/python` 을 추가하세요.
- **WSL2 는 부팅 시 cron 이 꺼져 있을 수 있습니다.** `sudo service cron start` 로 켜거나, `/etc/wsl.conf` 에 `[boot] command="service cron start"` 를 넣거나, `schedule_batch.sh loop` 를 사용하세요.
- `cli/logs/` 와 `cli/reports/` 는 `.gitignore` 에 등록되어 있습니다. 리포트를 git 으로 추적하려면 `.gitignore` 에서 `cli/reports/` 줄을 제거하세요.
