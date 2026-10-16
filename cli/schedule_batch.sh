#!/usr/bin/env bash
# ============================================================
# cli/schedule_batch.sh
#
# batch_fetch_korea_data.sh 를 30분 단위로 실행하도록 cron 에 등록/해제한다.
#
# 사용법:
#   cli/schedule_batch.sh install      # crontab 에 30분 주기 등록 (이미 있으면 갱신)
#   cli/schedule_batch.sh remove       # crontab 에서 제거
#   cli/schedule_batch.sh status       # 등록 여부, cron 서비스 상태, 최근 실행 결과 표시
#   cli/schedule_batch.sh run-now      # cron 과 같은 환경으로 즉시 1회 실행
#   cli/schedule_batch.sh loop         # cron 없이 포그라운드에서 30분마다 반복 (WSL 등에서 유용)
#
# 환경변수:
#   CRON_SCHEDULE    cron 표현식 (기본: "*/30 * * * *" = 매 30분)
#   BATCH_COMMANDS   배치가 실행할 명령 (기본: "krx vkospi ecos") - crontab 줄에 함께 기록됨
#   LOOP_INTERVAL    loop 모드 간격(초) (기본: 1800)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BATCH_SH="${SCRIPT_DIR}/batch_fetch_korea_data.sh"
CRON_LOG="${SCRIPT_DIR}/logs/cron.log"
REPORT_FILE="${SCRIPT_DIR}/reports/fetch_report.md"

CRON_SCHEDULE="${CRON_SCHEDULE:-*/30 * * * *}"
BATCH_COMMANDS="${BATCH_COMMANDS:-krx vkospi ecos}"
LOOP_INTERVAL="${LOOP_INTERVAL:-1800}"

# crontab 안에서 이 항목을 식별하는 태그
TAG="# market-stress-korea-fetch"

usage() {
    sed -n '2,/^# ====*$/p' "${BASH_SOURCE[0]}" | sed '1,2d;$d' | sed 's/^# \{0,1\}//'
}

die() { echo "[ERROR] $*" >&2; exit 1; }

cron_line() {
    # cron 은 PATH 가 최소이므로 절대경로 사용. 출력은 cron.log 에 누적.
    echo "${CRON_SCHEDULE} cd ${PROJECT_ROOT} && BATCH_COMMANDS=\"${BATCH_COMMANDS}\" ${BATCH_SH} >> ${CRON_LOG} 2>&1 ${TAG}"
}

current_crontab() {
    crontab -l 2>/dev/null || true
}

check_cron_service() {
    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet cron 2>/dev/null; then
        echo "running (systemd)"
    elif command -v service >/dev/null 2>&1 && service cron status >/dev/null 2>&1; then
        echo "running"
    elif pgrep -x cron >/dev/null 2>&1 || pgrep -x crond >/dev/null 2>&1; then
        echo "running (process)"
    else
        echo "NOT RUNNING"
    fi
}

cmd_install() {
    [[ -x "${BATCH_SH}" ]] || die "실행 파일이 없습니다: ${BATCH_SH}"
    command -v crontab >/dev/null 2>&1 || die "crontab 명령이 없습니다. (sudo apt install cron)"

    mkdir -p "${SCRIPT_DIR}/logs"

    local existing new_tab
    existing="$(current_crontab | grep -vF "${TAG}" || true)"
    new_tab="$(printf '%s\n%s\n' "${existing}" "$(cron_line)" | sed '/^$/d')"

    printf '%s\n' "${new_tab}" | crontab -

    echo "[INFO] crontab 등록 완료:"
    echo "       $(cron_line)"
    echo
    echo "[INFO] cron 서비스: $(check_cron_service)"
    if [[ "$(check_cron_service)" == "NOT RUNNING" ]]; then
        echo "[WARN] cron 서비스가 실행 중이 아닙니다. 다음 중 하나를 실행하세요:"
        echo "       sudo service cron start          # Ubuntu / WSL2"
        echo "       sudo systemctl enable --now cron # systemd"
        echo "       또는: cli/schedule_batch.sh loop  # cron 없이 포그라운드 반복"
    fi
    echo
    echo "[INFO] 리포트: ${REPORT_FILE}"
    echo "[INFO] cron 출력 로그: ${CRON_LOG}"
}

cmd_remove() {
    local existing
    existing="$(current_crontab)"
    if ! grep -qF "${TAG}" <<< "${existing}"; then
        echo "[INFO] 등록된 항목이 없습니다."
        return 0
    fi
    local remaining
    remaining="$(grep -vF "${TAG}" <<< "${existing}" || true)"
    if [[ -z "${remaining}" ]]; then
        crontab -r 2>/dev/null || true
    else
        printf '%s\n' "${remaining}" | crontab -
    fi
    echo "[INFO] crontab 에서 제거했습니다."
}

cmd_status() {
    echo "=== cron 서비스 ==="
    echo "$(check_cron_service)"
    echo
    echo "=== crontab 항목 ==="
    if current_crontab | grep -F "${TAG}"; then :; else echo "(등록 안 됨)"; fi
    echo
    echo "=== 최근 리포트 항목 ==="
    if [[ -f "${REPORT_FILE}" ]]; then
        # 마지막 '## ' 헤더부터 끝까지
        awk '/^## /{buf=""} {buf=buf $0 "\n"} END{printf "%s", buf}' "${REPORT_FILE}"
    else
        echo "(아직 실행된 적 없음: ${REPORT_FILE})"
    fi
    echo
    echo "=== cron.log 마지막 10줄 ==="
    if [[ -f "${CRON_LOG}" ]]; then tail -n 10 "${CRON_LOG}"; else echo "(없음)"; fi
}

cmd_run_now() {
    mkdir -p "${SCRIPT_DIR}/logs"
    # cron 과 비슷한 최소 환경으로 실행해 cron 에서의 동작을 미리 확인
    env -i HOME="${HOME}" PATH="/usr/local/bin:/usr/bin:/bin" SHELL="/bin/sh" \
        BATCH_COMMANDS="${BATCH_COMMANDS}" \
        bash -c "cd '${PROJECT_ROOT}' && '${BATCH_SH}'" 2>&1 | tee -a "${CRON_LOG}"
}

cmd_loop() {
    mkdir -p "${SCRIPT_DIR}/logs"
    echo "[INFO] loop 모드 시작 — ${LOOP_INTERVAL}초마다 실행. 중지: Ctrl+C"
    echo "[INFO] 백그라운드 실행 예: nohup cli/schedule_batch.sh loop > cli/logs/loop.out 2>&1 &"
    trap 'echo; echo "[INFO] loop 종료"; exit 0' INT TERM
    while true; do
        BATCH_COMMANDS="${BATCH_COMMANDS}" "${BATCH_SH}" >> "${CRON_LOG}" 2>&1 || true
        echo "[INFO] $(date '+%F %T') 실행 완료 — 다음 실행까지 ${LOOP_INTERVAL}초 대기"
        sleep "${LOOP_INTERVAL}"
    done
}

main() {
    case "${1:-}" in
        install) cmd_install ;;
        remove)  cmd_remove ;;
        status)  cmd_status ;;
        run-now) cmd_run_now ;;
        loop)    cmd_loop ;;
        ""|-h|--help) usage ;;
        *) echo "[ERROR] 알 수 없는 command: $1" >&2; echo >&2; usage >&2; exit 1 ;;
    esac
}

main "$@"
