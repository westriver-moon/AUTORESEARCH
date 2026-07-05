#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${BIN_DIR}/researchops_common.sh"
SCRIPT_NAME="cancel_job.sh"

EXPERIMENT_ID=""
MODE="cancel"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --experiment-id) EXPERIMENT_ID="${2:-}"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "${EXPERIMENT_ID}" ]] || die "--experiment-id is required"
validate_experiment_id "${EXPERIMENT_ID}"

EXP_ROOT="$(experiment_root "${EXPERIMENT_ID}")"
STATUS_FILE="${EXP_ROOT}/status.json"
RESULTS_DIR="${EXP_ROOT}/results"
RUN_OUTPUT=""
LOG_FILE=""
PROJECT_ROOT=""
PYTHON_BIN=""
PMT_CONFIG=""
DATA_ROOT=""
PRETRAIN=""
GPU=""
COMMAND_TEXT=""
SESSION_NAME="$(tmux_session_name "${EXPERIMENT_ID}")"

if command -v tmux >/dev/null 2>&1 && tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  tmux kill-session -t "${SESSION_NAME}"
  write_status "${STATUS_FILE}" "canceled" "tmux session was canceled" 0
else
  write_status "${STATUS_FILE}" "not_running" "no matching tmux session was running" 0
fi

