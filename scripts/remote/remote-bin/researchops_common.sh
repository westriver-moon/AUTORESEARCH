#!/usr/bin/env bash
set -euo pipefail

REMOTE_ROOT="${REMOTE_ROOT:-/home/research/researchops}"
DEFAULT_PROJECT_ROOT="${PROJECT_ROOT:-${REMOTE_ROOT}/TVI-LFM}"
DEFAULT_PROJECT_PARENT="${DEFAULT_PROJECT_ROOT%/*}"
DEFAULT_PYTHON_BIN="${PYTHON_BIN:-/opt/conda/envs/tvi-lfm/bin/python}"
DEFAULT_DATA_ROOT="${DATA_ROOT:-/data/SYSU-MM01}"
DEFAULT_PMT_CONFIG="${PMT_CONFIG:-${DEFAULT_PROJECT_ROOT}/config/stage_a/pmt_vit_stage_a_pmt_recipe_288x144_768.yaml}"
DEFAULT_PRETRAIN="${PRETRAIN:-${DEFAULT_PROJECT_PARENT}/PMT-SYSU/pretrained/jx_vit_base_p16_224-80ecf9dd.pth}"
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

resolve_gpu() {
  local requested="${1:-}"
  if [[ -z "${requested}" ]]; then
    printf '%s\n' "${DEFAULT_GPU}"
    return
  fi

  local lower
  lower="$(printf '%s' "${requested}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${lower}" != "auto" ]]; then
    [[ "${requested}" =~ ^[0-9,]+$ ]] || die "--gpu must be 'auto' or contain only digits and commas: ${requested}"
    printf '%s\n' "${requested}"
    return
  fi

  command -v nvidia-smi >/dev/null 2>&1 || die "Gpu=auto requires nvidia-smi on the remote host"

  local selected
  selected="$(nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits 2>/dev/null | "${PYTHON_BIN}" -c '
import math
import sys

best = None
for line in sys.stdin:
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 3:
        continue
    try:
        index = int(parts[0])
        memory_used = int(float(parts[1]))
        util = 0 if parts[2].upper() == "N/A" else int(float(parts[2]))
    except ValueError:
        continue
    if memory_used <= 1024 and util <= 10:
        candidate = (memory_used, util, index)
        if best is None or candidate < best:
            best = candidate

if best is not None:
    print(best[2])
')"

  [[ -n "${selected}" ]] || die "Gpu=auto found no idle GPU; require memory.used <= 1024 MiB and utilization.gpu <= 10%"
  printf '%s\n' "${selected}"
}

prepare_tvilfm_config() {
  local source_config="$1"
  local config_used="$2"
  local run_output="$3"
  local data_root="$4"
  local pretrain="$5"
  local gpu="$6"

  mkdir -p "$(dirname "${config_used}")" "${run_output}"
  CONFIG_IN="${source_config}" \
  CONFIG_OUT="${config_used}" \
  RUN_OUTPUT="${run_output}" \
  DATA_ROOT="${data_root}" \
  PRETRAIN="${pretrain}" \
  GPU="${gpu}" \
  "${PYTHON_BIN}" - <<'PY'
import os
import yaml

config_in = os.environ["CONFIG_IN"]
config_out = os.environ["CONFIG_OUT"]
run_output = os.environ["RUN_OUTPUT"].rstrip("/") + "/"
data_root = os.environ["DATA_ROOT"].rstrip("/") + "/"
pretrain = os.environ["PRETRAIN"]
gpu = os.environ["GPU"]

with open(config_in, "r", encoding="utf-8") as f:
    data = yaml.load(f, Loader=yaml.FullLoader) or {}

data["output_path"] = run_output
data["sysu_data_path"] = data_root
data["pmt_pretrained"] = pretrain
data["CUDA_VISIBLE_DEVICES"] = gpu
data["gpu_id"] = "0"

with open(config_out, "w", encoding="utf-8") as f:
    yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
PY
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
    RUN_OUTPUT="${run_output}" RESULTS_DIR="${results_dir}" python3 - <<'PY'
import json
import os
import re
from pathlib import Path

run_output = Path(os.environ["RUN_OUTPUT"])
results_dir = Path(os.environ["RESULTS_DIR"])
metric_path = results_dir / "metrics.json"

number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"

def maybe_float(text):
    return float(text) if text is not None else None

def to_percent(value):
    if value is None:
        return None
    return value * 100.0 if abs(value) <= 1.0 else value

def parse_tvilfm_log(path):
    best_rank1 = best_map = best_minp = None
    evals = []
    pending = {"mINP": None, "mAP": None, "rank1": None, "lines": []}

    best_re = re.compile(
        rf"Best .*?mINP:\s*({number}).*?Best mAP:\s*({number}).*?Best Rank1:\s*({number})",
        re.IGNORECASE,
    )
    minp_re = re.compile(rf"^\s*mINP:\s*({number})", re.IGNORECASE)
    map_re = re.compile(rf"^\s*mAP:\s*({number})", re.IGNORECASE)
    rank_re = re.compile(rf"^\s*Rank:\s*\[?\s*({number})", re.IGNORECASE)

    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        best_match = best_re.search(line)
        if best_match:
            best_minp, best_map, best_rank1 = map(float, best_match.groups())

        minp_match = minp_re.search(line)
        map_match = map_re.search(line)
        rank_match = rank_re.search(line)
        if minp_match:
            pending = {"mINP": float(minp_match.group(1)), "mAP": None, "rank1": None, "lines": [(line_no, line)]}
        elif map_match:
            pending["mAP"] = float(map_match.group(1))
            pending["lines"].append((line_no, line))
        elif rank_match:
            pending["rank1"] = float(rank_match.group(1))
            pending["lines"].append((line_no, line))
            evals.append(
                {
                    "line": pending["lines"][0][0] if pending["lines"] else line_no,
                    "mINP": pending["mINP"],
                    "mAP": pending["mAP"],
                    "rank1": pending["rank1"],
                    "raw_block": "\n".join(raw for _, raw in pending["lines"]),
                }
            )
            pending = {"mINP": None, "mAP": None, "rank1": None, "lines": []}

    if evals:
        last = evals[-1]
        primary_metric = best_map if best_map is not None else last["mAP"]
        return {
            "available": True,
            "schema_version": "reid-metrics-v1",
            "source_format": "tvilfm_log",
            "source": str(path),
            "metric_name": "mAP",
            "direction": "higher",
            "primary_metric": primary_metric,
            "primary_metric_source": "best_mAP" if best_map is not None else "last_mAP",
            "mAP": last["mAP"],
            "rank1": last["rank1"],
            "mINP": last["mINP"],
            "last_mAP": last["mAP"],
            "last_rank1": last["rank1"],
            "last_mINP": last["mINP"],
            "mAP_percent": to_percent(last["mAP"]),
            "rank1_percent": to_percent(last["rank1"]),
            "mINP_percent": to_percent(last["mINP"]),
            "best_mAP": best_map,
            "best_rank1": best_rank1,
            "best_mINP": best_minp,
            "best_mAP_percent": to_percent(best_map),
            "best_rank1_percent": to_percent(best_rank1),
            "best_mINP_percent": to_percent(best_minp),
            "eval_count": len(evals),
            "raw_block": last["raw_block"],
        }
    return None

log_candidates = sorted(run_output.glob("**/logs/log.log"), key=lambda p: p.stat().st_mtime, reverse=True)
if not log_candidates:
    metric_path.write_text(
        json.dumps({"available": False, "reason": "metrics.jsonl or TVI-LFM log.log not found"}) + "\n",
        encoding="utf-8",
    )
    raise SystemExit(0)

metric = parse_tvilfm_log(log_candidates[0])
if metric is None:
    metric = {"available": False, "reason": "no TVI-LFM metric line found", "source": str(log_candidates[0])}

metric_path.write_text(json.dumps(metric, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  fi
}
