#!/usr/bin/env bash
# ============================================================
# cli/batch_fetch_korea_data.sh
#
# fetch_korea_data.sh 를 배치(cron)로 실행하기 위한 래퍼.
# 한 번 실행될 때마다:
#   1. 지정된 수집 명령(기본: krx vkospi ecos)을 순서대로 실행
#   2. 각 실행의 전체 출력을 cli/logs/ 에 로그 파일로 저장
#   3. 성공/실패, 소요시간, CSV 행 수 / 날짜 범위 / 증가 행 수를
#      cli/reports/fetch_report.md 에 마크다운 로그로 append
#
# 사용법:
#   cli/batch_fetch_korea_data.sh                 # 기본 명령 전체 실행
#   cli/batch_fetch_korea_data.sh vkospi          # 특정 명령만
#   cli/batch_fetch_korea_data.sh krx vkospi      # 여러 개
#
# 환경변수:
#   BATCH_COMMANDS       인자가 없을 때 실행할 명령 목록 (기본: "krx vkospi ecos")
#   LOG_RETENTION_DAYS   이 일수보다 오래된 로그 파일 삭제 (기본: 14, 0 이면 삭제 안 함)
#   REPORT_FILE          리포트 md 경로 (기본: cli/reports/fetch_report.md)
#
# 동시 실행 방지: flock 으로 잠금. 이전 배치가 아직 실행 중이면
# 이번 실행은 건너뛰고 리포트에 SKIPPED 로 기록한다.
# ============================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

FETCH_SH="${SCRIPT_DIR}/fetch_korea_data.sh"
LOG_DIR="${SCRIPT_DIR}/logs"
REPORT_DIR="${SCRIPT_DIR}/reports"
STATE_DIR="${REPORT_DIR}/.state"
REPORT_FILE="${REPORT_FILE:-${REPORT_DIR}/fetch_report.md}"
LOCK_FILE="${LOG_DIR}/.batch.lock"

LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-14}"
BATCH_COMMANDS="${BATCH_COMMANDS:-krx vkospi ecos}"

# 명령 → 출력 CSV 매핑
declare -A OUTPUT_OF=(
    [krx]="data/raw/korea/krx_indices.csv"
    [vkospi]="data/raw/korea/vkospi.csv"
    [ecos]="data/raw/korea/ecos_credit.csv"
)

mkdir -p "${LOG_DIR}" "${REPORT_DIR}" "${STATE_DIR}"

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

now_ts()   { date '+%Y-%m-%d %H:%M:%S'; }
now_slug() { date '+%Y%m%d_%H%M%S'; }

# 리포트 파일이 없으면 헤더 생성
init_report() {
    if [[ ! -f "${REPORT_FILE}" ]]; then
        cat > "${REPORT_FILE}" <<'HDR'
# Korea Market Data Fetch Report

`cli/batch_fetch_korea_data.sh` 가 실행될 때마다 아래에 결과가 시간순으로 추가됩니다.
각 항목은 실행 시각, 명령별 성공/실패, 수집된 CSV 의 행 수 / 날짜 범위 / 직전 실행 대비 증가 행 수를 담고 있습니다.

- 상태: ✅ SUCCESS / ❌ FAIL / ⏭️ SKIPPED (이전 배치가 아직 실행 중)
- 전체 출력 로그: `cli/logs/<timestamp>_<command>.log`

---
HDR
    fi
}

# CSV 요약: rows|first_date|last_date|size
csv_summary() {
    local path="$1"
    if [[ ! -f "${path}" ]]; then
        echo "0|-|-|0"
        return
    fi
    local rows first last size
    rows=$(( $(wc -l < "${path}") - 1 ))
    (( rows < 0 )) && rows=0
    if (( rows > 0 )); then
        first=$(sed -n 2p "${path}" | cut -d, -f1)
        last=$(tail -n 1 "${path}" | cut -d, -f1)
    else
        first="-"; last="-"
    fi
    size=$(du -h "${path}" | cut -f1)
    echo "${rows}|${first}|${last}|${size}"
}

# 직전 행 수 읽기 / 저장
prev_rows() {
    local key="$1"
    local f="${STATE_DIR}/${key}.rows"
    [[ -f "${f}" ]] && cat "${f}" || echo 0
}
save_rows() {
    echo "$2" > "${STATE_DIR}/$1.rows"
}

# 로그에서 핵심 지표 추출
log_metrics() {
    local log="$1"
    local warn err failed
    warn=$(grep -c '^\[WARNING\]' "${log}" 2>/dev/null || true)
    err=$(grep -c '^\[ERROR\]'   "${log}" 2>/dev/null || true)
    # "Completely failed API request dates: N" 또는 "Failed dates: N"
    failed=$(grep -oE '(Completely failed API request dates|Failed dates): *[0-9]+' "${log}" \
             | grep -oE '[0-9]+$' | tail -n 1)
    echo "${warn:-0}|${err:-0}|${failed:-0}"
}

format_duration() {
    local s="$1"
    printf '%dm %02ds' $(( s / 60 )) $(( s % 60 ))
}

# 오래된 로그 정리
cleanup_logs() {
    if [[ "${LOG_RETENTION_DAYS}" =~ ^[0-9]+$ ]] && (( LOG_RETENTION_DAYS > 0 )); then
        find "${LOG_DIR}" -name '*.log' -type f -mtime "+${LOG_RETENTION_DAYS}" -delete 2>/dev/null || true
    fi
}

# ------------------------------------------------------------
# 한 명령 실행 → 리포트 행 생성
# ------------------------------------------------------------

run_one() {
    local cmd="$1"
    local slug="$2"
    local log="${LOG_DIR}/${slug}_${cmd}.log"
    local out="${OUTPUT_OF[${cmd}]:-}"

    local start end dur rc
    start=$(date +%s)

    "${FETCH_SH}" "${cmd}" > "${log}" 2>&1
    rc=$?

    end=$(date +%s)
    dur=$(( end - start ))

    local summary rows first last size
    summary=$(csv_summary "${PROJECT_ROOT}/${out}")
    IFS='|' read -r rows first last size <<< "${summary}"

    local before added
    before=$(prev_rows "${cmd}")
    added=$(( rows - before ))
    save_rows "${cmd}" "${rows}"

    local metrics warn err failed
    metrics=$(log_metrics "${log}")
    IFS='|' read -r warn err failed <<< "${metrics}"

    local status
    if (( rc == 0 )); then
        status="✅ SUCCESS"
    else
        status="❌ FAIL (exit ${rc})"
        OVERALL_FAIL=1
    fi

    # 표 행
    TABLE_ROWS+="| \`${cmd}\` | ${status} | $(format_duration "${dur}") | \`${out}\` | ${rows} | ${added:+${added}} | ${first} → ${last} | ${size} | ${warn} / ${err} / ${failed} | [log](../logs/${slug}_${cmd}.log) |"$'\n'

    # 실패 시 로그 꼬리 첨부
    if (( rc != 0 )); then
        ERROR_BLOCKS+="<details><summary>❌ \`${cmd}\` 오류 로그 (마지막 30줄)</summary>"$'\n\n```\n'
        ERROR_BLOCKS+="$(tail -n 30 "${log}")"$'\n```\n\n</details>\n\n'
    elif (( failed > 0 )); then
        ERROR_BLOCKS+="<details><summary>⚠️ \`${cmd}\` 실패한 날짜 ${failed}건</summary>"$'\n\n```\n'
        ERROR_BLOCKS+="$(grep -A 40 'FAILED REQUEST DATES\|Completely failed API request dates' "${log}" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | head -n 40)"$'\n```\n\n</details>\n\n'
    fi
}

# ------------------------------------------------------------
# 리포트 항목 작성
# ------------------------------------------------------------

append_report() {
    local started="$1" finished="$2" total_dur="$3" cmds="$4"
    local headline
    if (( OVERALL_FAIL )); then
        headline="❌ FAIL"
    else
        headline="✅ SUCCESS"
    fi

    {
        echo
        echo "## ${started} — ${headline}"
        echo
        echo "- 실행 명령: \`${cmds}\`"
        echo "- 시작: ${started} / 종료: ${finished} / 총 소요: $(format_duration "${total_dur}")"
        echo "- 호스트: \`$(hostname)\` / 실행자: \`$(whoami)\`"
        echo
        echo "| command | status | 소요 | 출력 파일 | 행 수 | 증가 | 날짜 범위 | 크기 | WARN / ERR / 실패날짜 | 로그 |"
        echo "|---|---|---|---|---:|---:|---|---:|---|---|"
        printf '%s' "${TABLE_ROWS}"
        echo
        if [[ -n "${ERROR_BLOCKS}" ]]; then
            printf '%s' "${ERROR_BLOCKS}"
        fi
        echo "---"
    } >> "${REPORT_FILE}"
}

append_skipped() {
    local started="$1"
    {
        echo
        echo "## ${started} — ⏭️ SKIPPED"
        echo
        echo "- 이전 배치가 아직 실행 중이어서 이번 실행을 건너뜀 (lock: \`cli/logs/.batch.lock\`)"
        echo "- 전체 수집은 15분 이상 걸릴 수 있으므로 첫 실행 직후에는 정상적인 현상입니다."
        echo
        echo "---"
    } >> "${REPORT_FILE}"
}

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

main() {
    cd "${PROJECT_ROOT}"
    init_report

    local cmds="${*:-${BATCH_COMMANDS}}"
    local started
    started=$(now_ts)

    # 실행할 명령 검증
    for c in ${cmds}; do
        if [[ -z "${OUTPUT_OF[${c}]:-}" ]]; then
            echo "[ERROR] 배치에서 지원하지 않는 command: ${c} (krx / vkospi / ecos 만 가능)" >&2
            exit 1
        fi
    done

    # 잠금 (이미 실행 중이면 SKIPPED 기록 후 종료)
    exec 9> "${LOCK_FILE}"
    if ! flock -n 9; then
        echo "[WARN] 이전 배치 실행 중 → 건너뜀"
        append_skipped "${started}"
        exit 0
    fi

    OVERALL_FAIL=0
    TABLE_ROWS=""
    ERROR_BLOCKS=""

    local slug t0 t1
    slug=$(now_slug)
    t0=$(date +%s)

    echo "[INFO] batch start ${started} — commands: ${cmds}"
    for c in ${cmds}; do
        echo "[INFO] running ${c} ..."
        run_one "${c}" "${slug}"
    done

    t1=$(date +%s)
    local finished
    finished=$(now_ts)

    append_report "${started}" "${finished}" "$(( t1 - t0 ))" "${cmds}"
    cleanup_logs

    echo "[INFO] batch end ${finished} — report: ${REPORT_FILE}"
    (( OVERALL_FAIL )) && exit 1
    exit 0
}

main "$@"
