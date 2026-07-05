#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${BIN_DIR}/researchops_common.sh"
SCRIPT_NAME="check_job.sh"

EXPERIMENT_ID=""
MODE="check"

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
SESSION_NAME="$(tmux_session_name "${EXPERIMENT_ID}")"

tmux_running="false"
if command -v tmux >/dev/null 2>&1 && tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  tmux_running="true"
fi

if [[ ! -f "${STATUS_FILE}" ]]; then
  PROJECT_ROOT=""
  PYTHON_BIN=""
  PMT_CONFIG=""
  DATA_ROOT=""
  PRETRAIN=""
  GPU=""
  RESULTS_DIR="${EXP_ROOT}/results"
  RUN_OUTPUT=""
  LOG_FILE=""
  COMMAND_TEXT=""
  write_status "${STATUS_FILE}" "not_found" "no job status exists for experiment" 1
  exit 1
fi

STATUS_FILE="${STATUS_FILE}" TMUX_RUNNING="${tmux_running}" python3 - <<'PY'
import json
import os
import sys
from datetime import datetime, timezone

path = os.environ["STATUS_FILE"]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
data["checked_at"] = datetime.now(timezone.utc).isoformat()
data["tmux_running"] = os.environ.get("TMUX_RUNNING") == "true"
print(json.dumps(data, ensure_ascii=False))
sys.exit(1 if data.get("state") == "not_found" else 0)
PY
