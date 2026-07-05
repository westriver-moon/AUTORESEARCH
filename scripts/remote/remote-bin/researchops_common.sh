#!/usr/bin/env bash
set -euo pipefail

REMOTE_ROOT="${REMOTE_ROOT:-/home/cgv841/ybj}"
DEFAULT_PROJECT_ROOT="${PROJECT_ROOT:-${REMOTE_ROOT}/PMT-SYSU}"
DEFAULT_PYTHON_BIN="${PYTHON_BIN:-/home/cgv841/anaconda3/envs/reid/bin/python}"
DEFAULT_DATA_ROOT="${DATA_ROOT:-/home/cgv841/datasets/SYSU-MM01}"
DEFAULT_PMT_CONFIG="${PMT_CONFIG:-${DEFAULT_PROJECT_ROOT}/pmt_sysu/config/sysu_pmt.yaml}"
DEFAULT_PRETRAIN="${PRETRAIN:-${DEFAULT_PROJECT_ROOT}/pretrained/jx_vit_base_p16_224-80ecf9dd.pth}"
DEFAULT_GPU="${GPU:-0}"
SCRIPT_NAME="${SCRIPT_NAME:-$(basename "$0")}"

die() {
  printf '%s: %s\n' "${SCRIPT_NAME}" "$*" >&2
  exit 2
}

validate_experiment_id() {
  local experiment_id="$1"
  if [[ ! "${experiment_id}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$ ]]; then
    die "invalid experiment id: ${experiment_id}"
  fi
}

ensure_under_remote_root() {
  local path="$1"
  case "${path}" in
    "${REMOTE_ROOT}"|"${REMOTE_ROOT}"/*) ;;
    *) die "path must stay under ${REMOTE_ROOT}: ${path}" ;;
  esac
}

experiment_root() {
  local experiment_id="$1"
  validate_experiment_id "${experiment_id}"
  printf '%s/experiments/%s\n' "${REMOTE_ROOT}" "${experiment_id}"
}

tmux_session_name() {
  local experiment_id="$1"
  validate_experiment_id "${experiment_id}"
  local safe="${experiment_id//[^A-Za-z0-9_-]/_}"
  printf 'researchops_%s\n' "${safe}"
}

shell_quote() {
  local value="$1"
  printf "'%s'" "${value//\'/\'\\\'\'}"
}

resolve_pmt_config() {
  local config_path="${1:-}"
  if [[ -n "${config_path}" && "$(basename "${config_path}")" != "experiment-contract.yaml" ]]; then
    printf '%s\n' "${config_path}"
  else
    printf '%s\n' "${DEFAULT_PMT_CONFIG}"
  fi
}

require_file() {
  local path="$1"
  local label="$2"
  [[ -f "${path}" ]] || die "missing ${label}: ${path}"
}

require_dir() {
  local path="$1"
  local label="$2"
  [[ -d "${path}" ]] || die "missing ${label}: ${path}"
}

require_executable() {
  local path="$1"
  local label="$2"
  [[ -x "${path}" ]] || die "missing executable ${label}: ${path}"
}

write_status() {
  local status_file="$1"
  local state="$2"
  local message="$3"
  local exit_code="${4:-0}"

  mkdir -p "$(dirname "${status_file}")"
  STATUS_FILE="${status_file}" \
  STATUS_STATE="${state}" \
  STATUS_MESSAGE="${message}" \
  STATUS_EXIT_CODE="${exit_code}" \
  STATUS_SCRIPT="${SCRIPT_NAME}" \
  STATUS_EXPERIMENT_ID="${EXPERIMENT_ID:-}" \
  STATUS_MODE="${MODE:-}" \
  STATUS_PROJECT_ROOT="${PROJECT_ROOT:-}" \
  STATUS_PYTHON_BIN="${PYTHON_BIN:-}" \
  STATUS_PMT_CONFIG="${PMT_CONFIG:-}" \
  STATUS_DATA_ROOT="${DATA_ROOT:-}" \
  STATUS_PRETRAIN="${PRETRAIN:-}" \
  STATUS_GPU="${GPU:-}" \
  STATUS_OUTPUT_DIR="${RUN_OUTPUT:-}" \
  STATUS_RESULTS_DIR="${RESULTS_DIR:-}" \
  STATUS_LOG_FILE="${LOG_FILE:-}" \
  STATUS_SESSION="${SESSION_NAME:-}" \
  STATUS_COMMAND="${COMMAND_TEXT:-}" \
  python3 - <<'PY'
import json
import os
from datetime import datetime, timezone

def env(name):
    return os.environ.get(name, "")

data = {
    "schema_version": "1.0",
    "script": env("STATUS_SCRIPT"),
    "state": env("STATUS_STATE"),
    "message": env("STATUS_MESSAGE"),
    "exit_code": int(env("STATUS_EXIT_CODE") or "0"),
    "experiment_id": env("STATUS_EXPERIMENT_ID"),
    "mode": env("STATUS_MODE"),
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "project_root": env("STATUS_PROJECT_ROOT"),
    "python_bin": env("STATUS_PYTHON_BIN"),
    "pmt_config": env("STATUS_PMT_CONFIG"),
    "data_root": env("STATUS_DATA_ROOT"),
    "pretrain": env("STATUS_PRETRAIN"),
    "gpu": env("STATUS_GPU"),
    "output_dir": env("STATUS_OUTPUT_DIR"),
    "results_dir": env("STATUS_RESULTS_DIR"),
    "log_file": env("STATUS_LOG_FILE"),
    "tmux_session": env("STATUS_SESSION"),
    "command": env("STATUS_COMMAND"),
}

with open(env("STATUS_FILE"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(json.dumps(data, ensure_ascii=False))
PY
}

write_last_metric() {
  local run_output="$1"
  local results_dir="$2"
  mkdir -p "${results_dir}"
  if [[ -f "${run_output}/metrics.jsonl" ]]; then
    tail -n 1 "${run_output}/metrics.jsonl" > "${results_dir}/metrics.json"
  else
    printf '{"available": false, "reason": "metrics.jsonl not found"}\n' > "${results_dir}/metrics.json"
  fi
}

