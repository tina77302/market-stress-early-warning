#!/usr/bin/env bash
# ============================================================
# cli/fetch_korea_data.sh
#
# .env 의 API 키(KRX_API_KEY, ECOS_API_KEY)를 적용한 뒤
# src/korea/ 의 데이터 수집 스크립트를 CLI 로 실행한다.
#
# 사용법:
#   cli/fetch_korea_data.sh <command>
#
# command:
#   krx          KOSPI / KOSPI200 일별 지수   -> data/raw/korea/krx_indices.csv
#   vkospi       VKOSPI 변동성지수            -> data/raw/korea/vkospi.csv
#   ecos         ECOS 금리/신용 시계열        -> data/raw/korea/ecos_credit.csv
#   all          krx + vkospi + ecos 순서대로 실행
#   test-krx     KRX 지수 API 단일 날짜 호출 테스트
#   test-vkospi  VKOSPI API 단일 날짜 호출 테스트
#   test-ecos    ECOS API 호출 테스트
#   test         위 세 가지 테스트 모두 실행
#
# 환경변수:
#   PYTHON       사용할 python 실행 파일 (기본: .venv/venv 안의 python, 없으면 python3)
#   ENV_FILE     읽어올 env 파일 (기본: 프로젝트 루트의 .env)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
KOREA_DIR="src/korea"

ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

usage() {
    # 파일 상단 주석 블록(두 번째 줄 ~ 두 번째 구분선 직전)을 그대로 출력
    sed -n '2,/^# ====*$/p' "${BASH_SOURCE[0]}" | sed '1,2d;$d' | sed 's/^# \{0,1\}//'
}

die() {
    echo "[ERROR] $*" >&2
    exit 1
}

# ------------------------------------------------------------
# 1. .env 로드 (스크립트 내부 load_dotenv 와 별개로 셸에도 export)
# ------------------------------------------------------------

load_env() {
    if [[ ! -f "${ENV_FILE}" ]]; then
        die ".env 파일이 없습니다: ${ENV_FILE}  (.env.example 을 복사해 만드세요)"
    fi

    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a

    echo "[INFO] env loaded: ${ENV_FILE}"
}

require_key() {
    local name="$1"
    local value="${!name:-}"

    if [[ -z "${value}" ]]; then
        die "${name} 가 ${ENV_FILE} 에 설정되어 있지 않습니다."
    fi

    # 키 값은 출력하지 않고 길이만 표시
    echo "[INFO] ${name} set (${#value} chars)"
}

# ------------------------------------------------------------
# 2. python 선택
# ------------------------------------------------------------

pick_python() {
    if [[ -n "${PYTHON:-}" ]]; then
        :
    elif [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
        PYTHON="${PROJECT_ROOT}/.venv/bin/python"
    elif [[ -x "${PROJECT_ROOT}/venv/bin/python" ]]; then
        PYTHON="${PROJECT_ROOT}/venv/bin/python"
    else
        PYTHON="$(command -v python3 || true)"
    fi

    [[ -n "${PYTHON}" ]] || die "python 을 찾을 수 없습니다."

    "${PYTHON}" -c "import pandas, requests, dotenv" 2>/dev/null \
        || die "python 패키지가 부족합니다 (${PYTHON}). 다음을 실행하세요: ${PYTHON} -m pip install -r requirements.txt"

    echo "[INFO] python: ${PYTHON}"
}

# ------------------------------------------------------------
# 3. 스크립트 실행
# ------------------------------------------------------------

run_py() {
    local script="$1"
    echo
    echo "============================================================"
    echo "RUN ${script}"
    echo "============================================================"
    "${PYTHON}" "${PROJECT_ROOT}/${KOREA_DIR}/${script}"
}

cmd_krx()         { require_key KRX_API_KEY;  run_py download_krx_indices.py; }
cmd_vkospi()      { require_key KRX_API_KEY;  run_py download_vkospi.py; }
cmd_ecos()        { require_key ECOS_API_KEY; run_py download_ecos_credit.py; }
cmd_test_krx()    { require_key KRX_API_KEY;  run_py test_krx_api.py; }
cmd_test_vkospi() { require_key KRX_API_KEY;  run_py test_vkospi_api.py; }
cmd_test_ecos()   { require_key ECOS_API_KEY; run_py test_ecos_credit.py; }

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

main() {
    local command="${1:-}"

    if [[ -z "${command}" || "${command}" == "-h" || "${command}" == "--help" ]]; then
        usage
        exit 0
    fi

    case "${command}" in
        krx|vkospi|ecos|all|test-krx|test-vkospi|test-ecos|test) ;;
        *)
            echo "[ERROR] 알 수 없는 command: ${command}" >&2
            echo >&2
            usage >&2
            exit 1
            ;;
    esac

    # 스크립트 안의 상대경로(data/raw/korea/...)가 맞도록 프로젝트 루트에서 실행
    cd "${PROJECT_ROOT}"

    load_env
    pick_python

    case "${command}" in
        krx)         cmd_krx ;;
        vkospi)      cmd_vkospi ;;
        ecos)        cmd_ecos ;;
        all)         cmd_krx; cmd_vkospi; cmd_ecos ;;
        test-krx)    cmd_test_krx ;;
        test-vkospi) cmd_test_vkospi ;;
        test-ecos)   cmd_test_ecos ;;
        test)        cmd_test_krx; cmd_test_vkospi; cmd_test_ecos ;;
    esac
}

main "$@"
