#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${BIN_DIR}/researchops_common.sh"
SCRIPT_NAME="run_train.sh"

EXPERIMENT_ID=""
CONFIG_PATH=""
PROJECT_ROOT="${DEFAULT_PROJECT_ROOT}"
PYTHON_BIN="${DEFAULT_PYTHON_BIN}"
DATA_ROOT="${DEFAULT_DATA_ROOT}"
PRETRAIN="${DEFAULT_PRETRAIN}"
GPU="${DEFAULT_GPU}"
CONFIRM_FULL_TRAINING=0
DRY_RUN=0
MODE="train"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --experiment-id) EXPERIMENT_ID="${2:-}"; shift 2 ;;
    --config) CONFIG_PATH="${2:-}"; shift 2 ;;
    --project-root) PROJECT_ROOT="${2:-}"; shift 2 ;;
    --python) PYTHON_BIN="${2:-}"; shift 2 ;;
    --data-root) DATA_ROOT="${2:-}"; shift 2 ;;
    --pretrained) PRETRAIN="${2:-}"; shift 2 ;;
    --gpu) GPU="${2:-}"; shift 2 ;;
    --confirm-full-training) CONFIRM_FULL_TRAINING=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "${EXPERIMENT_ID}" ]] || die "--experiment-id is required"
validate_experiment_id "${EXPERIMENT_ID}"
[[ "${CONFIRM_FULL_TRAINING}" -eq 1 ]] || die "--confirm-full-training is required"
ensure_under_remote_root "${PROJECT_ROOT}"

PMT_CONFIG="$(resolve_pmt_config "${CONFIG_PATH}")"
require_dir "${PROJECT_ROOT}" "project root"
require_executable "${PYTHON_BIN}" "python"
require_file "${PMT_CONFIG}" "TVI-LFM config"
require_file "${PRETRAIN}" "pretrained weights"
command -v tmux >/dev/null 2>&1 || die "tmux is required for full training"
GPU="$(resolve_gpu "${GPU}")"

EXP_ROOT="$(experiment_root "${EXPERIMENT_ID}")"
RESULTS_DIR="${EXP_ROOT}/results"
RUN_OUTPUT="${RESULTS_DIR}/train"
LOG_DIR="${RESULTS_DIR}/logs"
LOG_FILE="${LOG_DIR}/train.log"
STATUS_FILE="${EXP_ROOT}/status.json"
SESSION_NAME="$(tmux_session_name "${EXPERIMENT_ID}")"
WRAPPER="${EXP_ROOT}/train_wrapper.sh"
CONFIG_USED="${RESULTS_DIR}/config_used.yaml"
mkdir -p "${LOG_DIR}" "${RUN_OUTPUT}"
prepare_tvilfm_config "${PMT_CONFIG}" "${CONFIG_USED}" "${RUN_OUTPUT}" "${DATA_ROOT}" "${PRETRAIN}" "${GPU}"

COMMAND_TEXT="tmux new-session -d -s ${SESSION_NAME} ${WRAPPER}"

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  die "tmux session already exists: ${SESSION_NAME}"
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  write_status "${STATUS_FILE}" "dry_run" "full training dry run; tmux was not started" 0
  exit 0
fi

cat > "${WRAPPER}" <<EOF
#!/usr/bin/env bash
set -u
source $(shell_quote "${BIN_DIR}/researchops_common.sh")
SCRIPT_NAME="train_wrapper.sh"
EXPERIMENT_ID=$(shell_quote "${EXPERIMENT_ID}")
MODE="train"
PROJECT_ROOT=$(shell_quote "${PROJECT_ROOT}")
PYTHON_BIN=$(shell_quote "${PYTHON_BIN}")
PMT_CONFIG=$(shell_quote "${PMT_CONFIG}")
CONFIG_USED=$(shell_quote "${CONFIG_USED}")
DATA_ROOT=$(shell_quote "${DATA_ROOT}")
PRETRAIN=$(shell_quote "${PRETRAIN}")
GPU=$(shell_quote "${GPU}")
RESULTS_DIR=$(shell_quote "${RESULTS_DIR}")
RUN_OUTPUT=$(shell_quote "${RUN_OUTPUT}")
LOG_FILE=$(shell_quote "${LOG_FILE}")
STATUS_FILE=$(shell_quote "${STATUS_FILE}")
SESSION_NAME=$(shell_quote "${SESSION_NAME}")
COMMAND_TEXT=$(shell_quote "CUDA_VISIBLE_DEVICES=${GPU} ${PYTHON_BIN} main.py --config_select ${CONFIG_USED}")
write_status "\${STATUS_FILE}" "running" "full training started in tmux" 0 >/dev/null
set +e
(
  cd "\${PROJECT_ROOT}"
  export CUDA_VISIBLE_DEVICES="\${GPU}"
  "\${PYTHON_BIN}" main.py \\
    --config_select "\${CONFIG_USED}" \\
    > "\${LOG_FILE}" 2>&1
)
exit_code=\$?
set -e
write_last_metric "\${RUN_OUTPUT}" "\${RESULTS_DIR}"
if [[ "\${exit_code}" -eq 0 ]]; then
  write_status "\${STATUS_FILE}" "succeeded" "full training completed" "\${exit_code}" >/dev/null
else
  write_status "\${STATUS_FILE}" "failed" "full training failed; see log_file" "\${exit_code}" >/dev/null
fi
exit "\${exit_code}"
EOF
chmod 700 "${WRAPPER}"

tmux new-session -d -s "${SESSION_NAME}" "${WRAPPER}"
write_status "${STATUS_FILE}" "submitted" "full training submitted to tmux" 0
