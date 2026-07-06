#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${BIN_DIR}/researchops_common.sh"
SCRIPT_NAME="run_autoresearch_trial.sh"

EXPERIMENT_ID=""
CONFIG_PATH=""
PROJECT_ROOT="${DEFAULT_PROJECT_ROOT}"
PYTHON_BIN="${DEFAULT_PYTHON_BIN}"
DATA_ROOT="${DEFAULT_DATA_ROOT}"
PRETRAIN="${DEFAULT_PRETRAIN}"
GPU="${DEFAULT_GPU}"
SMOKE_BATCHES="${SMOKE_BATCHES:-1}"
MAX_SECONDS="${MAX_SECONDS:-300}"
DRY_RUN=0
MODE="trial"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --experiment-id) EXPERIMENT_ID="${2:-}"; shift 2 ;;
    --config) CONFIG_PATH="${2:-}"; shift 2 ;;
    --project-root) PROJECT_ROOT="${2:-}"; shift 2 ;;
    --python) PYTHON_BIN="${2:-}"; shift 2 ;;
    --data-root) DATA_ROOT="${2:-}"; shift 2 ;;
    --pretrained) PRETRAIN="${2:-}"; shift 2 ;;
    --gpu) GPU="${2:-}"; shift 2 ;;
    --smoke-batches) SMOKE_BATCHES="${2:-}"; shift 2 ;;
    --max-seconds) MAX_SECONDS="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "${EXPERIMENT_ID}" ]] || die "--experiment-id is required"
validate_experiment_id "${EXPERIMENT_ID}"
ensure_under_remote_root "${PROJECT_ROOT}"
[[ "${SMOKE_BATCHES}" =~ ^[0-9]+$ ]] || die "--smoke-batches must be a positive integer"
[[ "${MAX_SECONDS}" =~ ^[0-9]+$ ]] || die "--max-seconds must be a positive integer"
[[ "${SMOKE_BATCHES}" -ge 1 ]] || die "--smoke-batches must be at least 1"
[[ "${MAX_SECONDS}" -ge 1 ]] || die "--max-seconds must be at least 1"

PMT_CONFIG="$(resolve_pmt_config "${CONFIG_PATH}")"
require_dir "${PROJECT_ROOT}" "project root"
require_executable "${PYTHON_BIN}" "python"
require_file "${PMT_CONFIG}" "TVI-LFM config"
require_file "${PRETRAIN}" "pretrained weights"
command -v timeout >/dev/null 2>&1 || die "timeout is required for bounded autoresearch trials"
GPU="$(resolve_gpu "${GPU}")"

EXP_ROOT="$(experiment_root "${EXPERIMENT_ID}")"
RESULTS_DIR="${EXP_ROOT}/results"
RUN_OUTPUT="${RESULTS_DIR}/trial"
LOG_DIR="${RESULTS_DIR}/logs"
LOG_FILE="${LOG_DIR}/trial.log"
STATUS_FILE="${EXP_ROOT}/status.json"
CONFIG_USED="${RESULTS_DIR}/config_used.yaml"
mkdir -p "${LOG_DIR}" "${RUN_OUTPUT}"
prepare_tvilfm_config "${PMT_CONFIG}" "${CONFIG_USED}" "${RUN_OUTPUT}" "${DATA_ROOT}" "${PRETRAIN}" "${GPU}"

COMMAND_TEXT="CUDA_VISIBLE_DEVICES=${GPU} timeout --foreground ${MAX_SECONDS} ${PYTHON_BIN} main.py --config_select ${CONFIG_USED}"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  write_status "${STATUS_FILE}" "dry_run" "autoresearch trial dry run; command was not executed" 0
  exit 0
fi

write_status "${STATUS_FILE}" "running" "autoresearch trial started" 0 >/dev/null
set +e
(
  cd "${PROJECT_ROOT}"
  export CUDA_VISIBLE_DEVICES="${GPU}"
  timeout --foreground "${MAX_SECONDS}" "${PYTHON_BIN}" main.py \
    --config_select "${CONFIG_USED}" \
    > "${LOG_FILE}" 2>&1
)
exit_code=$?
set -e

write_last_metric "${RUN_OUTPUT}" "${RESULTS_DIR}"

if [[ "${exit_code}" -eq 0 ]]; then
  write_status "${STATUS_FILE}" "succeeded" "autoresearch trial completed" "${exit_code}"
elif [[ "${exit_code}" -eq 124 ]]; then
  write_status "${STATUS_FILE}" "timeout" "autoresearch trial exceeded max seconds; see log_file" "${exit_code}"
else
  write_status "${STATUS_FILE}" "failed" "autoresearch trial failed; see log_file" "${exit_code}"
fi

exit "${exit_code}"
