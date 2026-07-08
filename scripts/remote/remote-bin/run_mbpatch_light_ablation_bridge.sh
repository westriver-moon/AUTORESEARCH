#!/usr/bin/env bash
set -euo pipefail

EXPERIMENT_ID="mbpatch_light_ablation_h5_ep33"
MODE="inspect"
PROJECT_ROOT="/home/cgv841/ybj/TVI-LFM"
PYTHON_BIN="/home/cgv841/anaconda3/envs/clipreid/bin/python"
DATA_ROOT="/home/cgv841/datasets/SYSU-MM01"
PRETRAIN="/home/cgv841/ybj/PMT-SYSU/pretrained/jx_vit_base_p16_224-80ecf9dd.pth"
GPU="auto"
GPUS=""
MAX_PARALLEL="4"
MAX_MEM="2000"
MAX_UTIL="20"
RERUN_FAILED="0"
REMOTE_ROOT="${REMOTE_ROOT:-/home/cgv841/ybj}"

die() {
  printf 'error: %s\n' "$*" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --experiment-id) EXPERIMENT_ID="${2:-}"; shift 2 ;;
    --project-root) PROJECT_ROOT="${2:-}"; shift 2 ;;
    --python) PYTHON_BIN="${2:-}"; shift 2 ;;
    --data-root) DATA_ROOT="${2:-}"; shift 2 ;;
    --pretrained) PRETRAIN="${2:-}"; shift 2 ;;
    --gpu) GPU="${2:-}"; shift 2 ;;
    --gpus) GPUS="${2:-}"; shift 2 ;;
    --max-parallel) MAX_PARALLEL="${2:-}"; shift 2 ;;
    --max-mem) MAX_MEM="${2:-}"; shift 2 ;;
    --max-util) MAX_UTIL="${2:-}"; shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --rerun-failed) RERUN_FAILED="1"; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ "${EXPERIMENT_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$ ]] || die "invalid experiment id"
case "${MODE}" in
  inspect|apply|smoke|start|status|collect|summarize|audit) ;;
  *) die "--mode must be inspect, apply, smoke, start, status, collect, summarize, or audit" ;;
esac
[[ -d "${PROJECT_ROOT}" ]] || die "project root not found: ${PROJECT_ROOT}"
[[ -x "${PYTHON_BIN}" ]] || die "python not executable: ${PYTHON_BIN}"

RESULTS_DIR="${REMOTE_ROOT}/experiments/${EXPERIMENT_ID}/results"
LOG_DIR="${RESULTS_DIR}/logs"
STATUS_FILE="${RESULTS_DIR}/status_${MODE}.json"
EXP_SLUG="mbpatch_light_ablation_h5_ep33"
TRAIN_OUTPUT_DIR="${PROJECT_ROOT}/train_outputs/${EXP_SLUG}"
mkdir -p "${LOG_DIR}"

write_status() {
  local state="$1"
  local message="$2"
  local exit_code="${3:-0}"
  "${PYTHON_BIN}" - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

status = {
    "schema_version": "1.0",
    "script": "run_mbpatch_light_ablation_bridge.sh",
    "state": "${state}",
    "message": "${message}",
    "exit_code": int("${exit_code}"),
    "experiment_id": "${EXPERIMENT_ID}",
    "mode": "${MODE}",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "project_root": "${PROJECT_ROOT}",
    "python_bin": "${PYTHON_BIN}",
    "data_root": "${DATA_ROOT}",
    "pretrain": "${PRETRAIN}",
    "gpu": "${GPU}",
    "gpus": "${GPUS}",
    "max_parallel": int("${MAX_PARALLEL}"),
    "max_mem": int("${MAX_MEM}"),
    "max_util": int("${MAX_UTIL}"),
    "results_dir": "${RESULTS_DIR}",
}
path = Path("${STATUS_FILE}")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(status, ensure_ascii=False, indent=2))
PY
}

inspect_project() {
  local inspect_dir="${LOG_DIR}/inspect"
  rm -rf "${inspect_dir}"
  mkdir -p "${inspect_dir}"
  (
    cd "${PROJECT_ROOT}"
    printf 'project_root=%s\n' "${PROJECT_ROOT}" > "${inspect_dir}/bridge_env.txt"
    printf 'python_bin=%s\n' "${PYTHON_BIN}" >> "${inspect_dir}/bridge_env.txt"
    printf 'data_root=%s\n' "${DATA_ROOT}" >> "${inspect_dir}/bridge_env.txt"
    printf 'pretrained=%s\n' "${PRETRAIN}" >> "${inspect_dir}/bridge_env.txt"
    printf 'mode=%s\n' "${MODE}" >> "${inspect_dir}/bridge_env.txt"
    git status --short > "${inspect_dir}/git_status.txt" 2>&1 || true
    git rev-parse --abbrev-ref HEAD > "${inspect_dir}/git_branch.txt" 2>&1 || true
    git rev-parse HEAD > "${inspect_dir}/git_head.txt" 2>&1 || true
    find . -maxdepth 3 -type f | sort > "${inspect_dir}/file_tree_depth3.txt" 2>&1 || true
    if command -v rg >/dev/null 2>&1; then
      rg -n "pmt_patch_embed|PatchEmbed|patch_embed|PMT_VIT|build_CLIP_from_openai_pretrained|encode_image" \
        . > "${inspect_dir}/patch_symbol_scan.txt" 2>&1 || true
    else
      grep -RInE "pmt_patch_embed|PatchEmbed|patch_embed|PMT_VIT|build_CLIP_from_openai_pretrained|encode_image" \
        . > "${inspect_dir}/patch_symbol_scan.txt" 2>&1 || true
    fi

    files=(
      "config/default.yaml"
      "config/stage_a/pmt_vit_stage_a_pmt_recipe_288x144_768.yaml"
      "config/stage_a/pmt_vit_stage_a_current_best.yaml"
      "main.py"
      "core/build.py"
      "core/train.py"
      "data_loader/loader.py"
      "data_loader/sampler.py"
      "tools/loss.py"
      "network/clip_model/clip_model.py"
      "network/clip_model/model.py"
      "network/clip_model/pmt_vit.py"
      "scripts/smoke_mbpatch_light_ablation_h5_ep33.py"
      "scripts/run_mbpatch_light_ablation_h5_ep33.py"
      "scripts/summarize_mbpatch_light_ablation_h5_ep33.py"
      "scripts/overnight_mbpatch_light_ablation_h5_ep33.sh"
    )
    for rel in "${files[@]}"; do
      if [[ -f "${rel}" ]]; then
        mkdir -p "${inspect_dir}/$(dirname "${rel}")"
        cp "${rel}" "${inspect_dir}/${rel}"
      else
        printf 'missing: %s\n' "${rel}" >> "${inspect_dir}/missing_files.txt"
      fi
    done

    while IFS= read -r rel; do
      [[ -f "${rel}" ]] || continue
      mkdir -p "${inspect_dir}/$(dirname "${rel}")"
      cp "${rel}" "${inspect_dir}/${rel}"
    done < <(find network -type f \( -name '*.py' -o -name '*.yaml' \) | sort)
    if [[ -d "config/stage_a/${EXP_SLUG}" ]]; then
      find "config/stage_a/${EXP_SLUG}" -type f -name '*.yaml' -print0 |
        while IFS= read -r -d '' rel; do
          mkdir -p "${inspect_dir}/$(dirname "${rel}")"
          cp "${rel}" "${inspect_dir}/${rel}"
        done
    fi
  )
}

select_idle_gpu() {
  if [[ -n "${GPUS}" ]]; then
    IFS=',' read -r -a candidate_gpus <<< "${GPUS}"
  elif [[ "${GPU}" != "auto" && -n "${GPU}" ]]; then
    candidate_gpus=("${GPU}")
  else
    candidate_gpus=()
  fi

  if ! command -v nvidia-smi >/dev/null 2>&1; then
    printf '%s\n' "${candidate_gpus[0]:-0}"
    return 0
  fi

  local smi
  smi="$(nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits 2>/dev/null || true)"
  if [[ -z "${smi}" ]]; then
    printf '%s\n' "${candidate_gpus[0]:-0}"
    return 0
  fi

  while IFS=',' read -r index mem util; do
    index="$(echo "${index}" | xargs)"
    mem="$(echo "${mem}" | xargs)"
    util="$(echo "${util}" | xargs)"
    if [[ ${#candidate_gpus[@]} -gt 0 ]]; then
      local allowed=0
      for candidate in "${candidate_gpus[@]}"; do
        [[ "${candidate}" == "${index}" ]] && allowed=1
      done
      [[ "${allowed}" -eq 1 ]] || continue
    fi
    if [[ "${mem}" =~ ^[0-9]+$ && "${util}" =~ ^[0-9]+$ ]]; then
      if (( mem < MAX_MEM && util < MAX_UTIL )); then
        printf '%s\n' "${index}"
        return 0
      fi
    fi
  done <<< "${smi}"

  printf '%s\n' "${candidate_gpus[0]:-0}"
}

apply_project_changes() {
  local apply_log="${LOG_DIR}/apply_mbpatch_light_ablation.log"
  (
    cd "${PROJECT_ROOT}"
    PROJECT_ROOT="${PROJECT_ROOT}" \
    PYTHON_BIN="${PYTHON_BIN}" \
    DATA_ROOT="${DATA_ROOT}" \
    PRETRAIN="${PRETRAIN}" \
    "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
import py_compile
import shutil
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(os.environ["PROJECT_ROOT"]).resolve()
EXP_SLUG = "mbpatch_light_ablation_h5_ep33"
BASE_CONFIG = ROOT / "config/stage_a/pmt_vit_stage_a_pmt_recipe_288x144_768.yaml"
CONFIG_DIR = ROOT / "config/stage_a" / EXP_SLUG
SCRIPT_DIR = ROOT / "scripts"
OUTPUT_DIR = ROOT / "train_outputs" / EXP_SLUG
MAIN_FILE = ROOT / "main.py"

EXPERIMENTS = [
    {
        "name": "m1_mb_16x16_16x8_h5_ep33",
        "branches": [
            {"patch_size": [16, 16], "stride_size": [12, 12]},
            {"patch_size": [16, 8], "stride_size": [12, 6]},
        ],
    },
    {
        "name": "m2_mb_16x16_8x16_h5_ep33",
        "branches": [
            {"patch_size": [16, 16], "stride_size": [12, 12]},
            {"patch_size": [8, 16], "stride_size": [6, 12]},
        ],
    },
    {
        "name": "m3_mb_16x16_8x8_h5_ep33",
        "branches": [
            {"patch_size": [16, 16], "stride_size": [12, 12]},
            {"patch_size": [8, 8], "stride_size": [6, 6]},
        ],
    },
    {
        "name": "m4_mb_16x16_32x16_h5_ep33",
        "branches": [
            {"patch_size": [16, 16], "stride_size": [12, 12]},
            {"patch_size": [32, 16], "stride_size": [24, 12]},
        ],
    },
    {
        "name": "m5_mb_16x16_16x8_8x16_h5_ep33",
        "branches": [
            {"patch_size": [16, 16], "stride_size": [12, 12]},
            {"patch_size": [16, 8], "stride_size": [12, 6]},
            {"patch_size": [8, 16], "stride_size": [6, 12]},
        ],
    },
    {
        "name": "m6_mb_16x16_8x8_32x16_h5_ep33",
        "branches": [
            {"patch_size": [16, 16], "stride_size": [12, 12]},
            {"patch_size": [8, 8], "stride_size": [6, 6]},
            {"patch_size": [32, 16], "stride_size": [24, 12]},
        ],
    },
]

FIXED = {
    "pretrain_choice": "PMT_VIT",
    "prj_output_dim": 768,
    "img_h": 288,
    "img_w": 144,
    "img_size": [288, 144],
    "sampler_type": "identity_auto_replace",
    "triplet_mining": "pmt_cross_modal_hard",
    "batch_size": 32,
    "num_pos": 4,
    "pmt_triplet_margin": 0.1,
    "pmt_recipe": True,
    "pmt_recipe_transforms": True,
    "pmt_progressive_epoch": 6,
    "pmt_msel_weight": 0.5,
    "pmt_dcl_weight": 0.5,
    "optimizer": "AdamW",
    "lr_visual": 0.0003,
    "lrscheduler": "cosine",
    "total_train_epoch": 33,
    "eval_start_epoch": 2,
    "eval_epoch": 2,
    "seed": 0,
    "training_mode": "RGB_IR",
    "joint_mode": "image_only",
    "loss_names": "pmt_recipe",
    "gpu_id": "0",
    "CUDA_VISIBLE_DEVICES": "0",
}


def backup_if_changed(path: Path, new_content: str, backup_root: Path) -> None:
    if not path.exists():
        return
    old_content = path.read_text(encoding="utf-8")
    if old_content == new_content:
        return
    rel = path.relative_to(ROOT)
    dst = backup_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def write_text(path: Path, content: str, backup_root: Path, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_if_changed(path, content, backup_root)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def make_configs(backup_root: Path) -> list[str]:
    if not BASE_CONFIG.is_file():
        raise FileNotFoundError(f"Base config not found: {BASE_CONFIG}")
    base = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    written = []
    for exp in EXPERIMENTS:
        cfg = dict(base)
        cfg.update(FIXED)
        cfg["output_path"] = f"logs/{EXP_SLUG}/{exp['name']}/"
        cfg["pmt_patch_embed"] = {
            "anchor_branch": 0,
            "branches": exp["branches"],
        }
        out_path = CONFIG_DIR / f"{exp['name']}.yaml"
        content = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
        write_text(out_path, content, backup_root)
        written.append(rel(out_path))
    return written


def patch_main_py(backup_root: Path) -> str:
    if not MAIN_FILE.is_file():
        raise FileNotFoundError(f"main.py not found: {MAIN_FILE}")

    text = MAIN_FILE.read_text(encoding="utf-8")

    import_anchor = 'import os\n# os.environ["CUDA_VISIBLE_DEVICES"] = "0"\nimport ast\nimport torch\n'
    import_replacement = (
        'import os\n'
        'os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")\n'
        '# os.environ["CUDA_VISIBLE_DEVICES"] = "0"\n'
        'import ast\n'
        'import gc\n'
        'import torch\n'
    )
    if "PYTORCH_CUDA_ALLOC_CONF" not in text:
        if import_anchor not in text:
            raise RuntimeError("Could not find main.py import block for allocator patch")
        text = text.replace(import_anchor, import_replacement, 1)
    elif "import gc\n" not in text:
        if "import ast\n" not in text:
            raise RuntimeError("Could not find main.py ast import for gc patch")
        text = text.replace("import ast\n", "import ast\nimport gc\n", 1)

    cleanup_snippet = (
        "                gc.collect()\n"
        "                if torch.cuda.is_available():\n"
        "                    torch.cuda.empty_cache()\n\n"
        "        performance_writer.close()"
    )
    cleanup_anchor = (
        '                                                                                    config.dataset,"Text_RGB",\n'
        '                                                                                    mINP_text, mAP_text, cmc_text))\n\n'
        '        performance_writer.close()'
    )
    cleanup_replacement = (
        '                                                                                    config.dataset,"Text_RGB",\n'
        '                                                                                    mINP_text, mAP_text, cmc_text))\n\n'
        '                gc.collect()\n'
        '                if torch.cuda.is_available():\n'
        '                    torch.cuda.empty_cache()\n\n'
        '        performance_writer.close()'
    )
    if cleanup_snippet not in text:
        if cleanup_anchor not in text:
            raise RuntimeError("Could not find main.py evaluation block for cleanup patch")
        text = text.replace(cleanup_anchor, cleanup_replacement, 1)

    write_text(MAIN_FILE, text, backup_root)
    return rel(MAIN_FILE)


SMOKE_SCRIPT = r'''
from __future__ import annotations

import gc
import math
import os
import sys
import traceback
from pathlib import Path

import torch
from torch.cuda import amp

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import build_model
from data_loader.loader import Loader
from tools.utils import load_train_configs

EXP_SLUG = "mbpatch_light_ablation_h5_ep33"
EXPERIMENTS = [
    "m1_mb_16x16_16x8_h5_ep33",
    "m2_mb_16x16_8x16_h5_ep33",
    "m3_mb_16x16_8x8_h5_ep33",
    "m4_mb_16x16_32x16_h5_ep33",
    "m5_mb_16x16_16x8_8x16_h5_ep33",
    "m6_mb_16x16_8x8_32x16_h5_ep33",
]


def _set_pid_num(config):
    if config.dataset == "sysu":
        config.pid_num = 395
    elif config.dataset == "regdb":
        config.pid_num = 206
    elif config.dataset == "llcm":
        config.pid_num = 713
    else:
        raise ValueError(f"Unsupported dataset: {config.dataset}")


def _labels_ok(labels, num_pos):
    if labels.numel() % num_pos != 0:
        return False
    chunks = labels.view(-1, num_pos)
    return bool(torch.all(chunks.eq(chunks[:, :1])).item())


def _to_device(batch, device):
    return {key: value.to(device) for key, value in batch.items()}


def run_one(exp_name):
    config_path = ROOT / "config/stage_a" / EXP_SLUG / f"{exp_name}.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    config = load_train_configs(str(config_path))
    config.mode = "train"
    config.num_workers = 0
    config.CUDA_VISIBLE_DEVICES = os.environ.get("CUDA_VISIBLE_DEVICES", "0")
    config.gpu_id = "0"
    _set_pid_num(config)

    print(f"[{exp_name}] loading dataloader from {config_path}", flush=True)
    loaders = Loader(config)
    loader = loaders.get_train_loader()
    batch = next(iter(loader))

    target_rgb = batch["target_rgb"]
    target_ir = batch["target_ir"]
    if target_rgb.shape != target_ir.shape:
        raise AssertionError(f"target shape mismatch: {tuple(target_rgb.shape)} vs {tuple(target_ir.shape)}")
    if not torch.equal(target_rgb, target_ir):
        raise AssertionError("target_rgb != target_ir")
    if not _labels_ok(target_rgb.long(), int(config.num_pos)):
        raise AssertionError(f"target_rgb is not grouped by num_pos={config.num_pos}")
    if not _labels_ok(target_ir.long(), int(config.num_pos)):
        raise AssertionError(f"target_ir is not grouped by num_pos={config.num_pos}")

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"[{exp_name}] building model on {device}", flush=True)
    model = build_model(config).to(device)
    model.set_train()
    batch = _to_device(batch, device)
    model.zero_grad(set_to_none=True)
    current_epoch = int(getattr(config, "pmt_progressive_epoch", 6))
    with amp.autocast(enabled=(device.type == "cuda")):
        ret = model(batch, mode=None, current_epoch=current_epoch)

    required = ["id_loss", "tri_loss", "msel_loss", "dcl_loss"]
    losses = []
    for key in required:
        if key not in ret:
            raise AssertionError(f"missing {key}; got keys={sorted(ret)}")
        value = ret[key]
        if not torch.is_tensor(value):
            raise AssertionError(f"{key} is not a tensor")
        if not torch.isfinite(value.detach().float()).all().item():
            raise AssertionError(f"{key} is not finite: {value}")
        losses.append(value)
    total_loss = sum(losses)
    if not torch.isfinite(total_loss.detach().float()).all().item():
        raise AssertionError("total_loss is not finite")
    total_loss.backward()

    loss_text = ", ".join(f"{key}={float(ret[key].detach().float().cpu()):.6f}" for key in required)
    print(f"{exp_name} PASS ({loss_text})", flush=True)
    del model, loaders, loader, batch, ret, total_loss
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def main():
    failed = []
    for exp_name in EXPERIMENTS:
        try:
            run_one(exp_name)
        except Exception as exc:
            print(f"{exp_name} FAIL: {exc}", flush=True)
            traceback.print_exc()
            failed.append(exp_name)
            break
    if failed:
        raise SystemExit(1)
    print("ALL MBPATCH LIGHT SMOKE TESTS PASS", flush=True)


if __name__ == "__main__":
    main()
'''


RUNNER_SCRIPT = r'''
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXP_SLUG = "mbpatch_light_ablation_h5_ep33"
OUTPUT_DIR = ROOT / "train_outputs" / EXP_SLUG
STATUS_PATH = OUTPUT_DIR / "status.json"
CONFIG_DIR = ROOT / "config/stage_a" / EXP_SLUG
RUNTIME_CONFIG_DIR = OUTPUT_DIR / "runtime_configs"
EXPERIMENTS = [
    "m1_mb_16x16_16x8_h5_ep33",
    "m2_mb_16x16_8x16_h5_ep33",
    "m3_mb_16x16_8x8_h5_ep33",
    "m4_mb_16x16_32x16_h5_ep33",
    "m5_mb_16x16_16x8_8x16_h5_ep33",
    "m6_mb_16x16_8x8_32x16_h5_ep33",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def load_status():
    if STATUS_PATH.is_file():
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    return {}


def save_status(status):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATUS_PATH)


def pid_alive(pid):
    if pid in (None, ""):
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


def base_record(exp_name):
    return {
        "config": f"config/stage_a/{EXP_SLUG}/{exp_name}.yaml",
        "status": "pending",
        "gpu": None,
        "start_time": None,
        "end_time": None,
        "return_code": None,
    }


def init_status(rerun_failed=False):
    status = load_status()
    changed = False
    for exp_name in EXPERIMENTS:
        if exp_name not in status:
            status[exp_name] = base_record(exp_name)
            changed = True
        elif status[exp_name].get("status") == "failed" and rerun_failed:
            status[exp_name].update(base_record(exp_name))
            changed = True
        elif status[exp_name].get("status") == "running":
            if not pid_alive(status[exp_name].get("pid")):
                status[exp_name]["status"] = "pending"
                status[exp_name]["return_code"] = None
                status[exp_name]["pid"] = None
                status[exp_name]["gpu"] = None
                changed = True
    if changed:
        save_status(status)
    return status


def parse_gpus(gpus_arg):
    if gpus_arg:
        return [int(part) for part in gpus_arg.split(",") if part.strip()]
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return [int(line.strip()) for line in out.splitlines() if line.strip()]
    except Exception:
        return [0]


def query_idle_gpus(candidate_gpus, max_mem, max_util):
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return list(candidate_gpus)
    allowed = set(candidate_gpus)
    idle = []
    for line in out.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        index, mem, util = map(int, parts[:3])
        if index in allowed and mem < max_mem and util < max_util:
            idle.append(index)
    return idle


def make_runtime_config(exp_name, gpu):
    src = CONFIG_DIR / f"{exp_name}.yaml"
    if not src.is_file():
        raise FileNotFoundError(src)
    cfg = yaml.safe_load(src.read_text(encoding="utf-8"))
    cfg["CUDA_VISIBLE_DEVICES"] = str(gpu)
    cfg["gpu_id"] = "0"
    RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    dst = RUNTIME_CONFIG_DIR / f"{exp_name}_gpu{gpu}.yaml"
    dst.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return dst


def launch(exp_name, gpu, status):
    exp_dir = OUTPUT_DIR / exp_name
    exp_dir.mkdir(parents=True, exist_ok=True)
    log_path = exp_dir / "launcher.log"
    runtime_config = make_runtime_config(exp_name, gpu)
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    cmd = [sys.executable, "main.py", "--config_select", str(runtime_config)]
    log = log_path.open("a", encoding="utf-8")
    log.write(f"\n[{now()}] START gpu={gpu} cmd={' '.join(cmd)}\n")
    log.flush()
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    status[exp_name].update(
        {
            "status": "running",
            "gpu": gpu,
            "pid": proc.pid,
            "runtime_config": str(runtime_config.relative_to(ROOT)),
            "start_time": now(),
            "end_time": None,
            "return_code": None,
            "launcher_log": str(log_path.relative_to(ROOT)),
        }
    )
    save_status(status)
    return proc, log


def pending_experiments(status):
    return [
        exp_name
        for exp_name in EXPERIMENTS
        if status[exp_name].get("status") in {"pending", "running"}
    ]


def active_gpus_from_status(status):
    active = set()
    for exp_name in EXPERIMENTS:
        record = status.get(exp_name, {})
        if record.get("status") != "running":
            continue
        if not pid_alive(record.get("pid")):
            continue
        gpu = record.get("gpu")
        if gpu is not None:
            active.add(gpu)
    return active


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--gpus", default="")
    parser.add_argument("--rerun-failed", action="store_true")
    parser.add_argument("--max-mem", type=int, default=2000)
    parser.add_argument("--max-util", type=int, default=20)
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()

    status = init_status(rerun_failed=args.rerun_failed)
    candidate_gpus = parse_gpus(args.gpus)
    running = {}
    logs = {}

    while True:
        for exp_name, proc in list(running.items()):
            rc = proc.poll()
            if rc is None:
                continue
            logs[exp_name].write(f"[{now()}] END return_code={rc}\n")
            logs[exp_name].close()
            status[exp_name]["status"] = "done" if rc == 0 else "failed"
            status[exp_name]["end_time"] = now()
            status[exp_name]["return_code"] = rc
            save_status(status)
            del running[exp_name]
            del logs[exp_name]

        queued = [
            exp_name
            for exp_name in EXPERIMENTS
            if status[exp_name].get("status") == "pending"
        ]
        active_gpus = active_gpus_from_status(status)
        idle_gpus = [gpu for gpu in query_idle_gpus(candidate_gpus, args.max_mem, args.max_util) if gpu not in active_gpus]
        slots = max(0, min(args.max_parallel, len(candidate_gpus)) - len(running))
        while queued and idle_gpus and slots > 0:
            exp_name = queued.pop(0)
            gpu = idle_gpus.pop(0)
            proc, log = launch(exp_name, gpu, status)
            running[exp_name] = proc
            logs[exp_name] = log
            slots -= 1

        unfinished = [exp for exp in EXPERIMENTS if status[exp].get("status") in {"pending", "running"}]
        if not unfinished and not running:
            break
        time.sleep(args.poll_seconds)

    failed = [exp for exp in EXPERIMENTS if status[exp].get("status") == "failed"]
    if failed:
        print(f"Failed experiments: {failed}", flush=True)
        raise SystemExit(1)
    print("All mbpatch light ablation experiments done.", flush=True)


if __name__ == "__main__":
    main()
'''


SUMMARIZER_SCRIPT = r'''
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXP_SLUG = "mbpatch_light_ablation_h5_ep33"
OUTPUT_DIR = ROOT / "train_outputs" / EXP_SLUG
LOG_ROOT = ROOT / "logs" / EXP_SLUG
CONFIG_DIR = ROOT / "config/stage_a" / EXP_SLUG
STATUS_PATH = OUTPUT_DIR / "status.json"
RESULTS_MD = OUTPUT_DIR / "RESULTS.md"
RESULTS_CSV = OUTPUT_DIR / "results.csv"
EXPERIMENTS = [
    "m1_mb_16x16_16x8_h5_ep33",
    "m2_mb_16x16_8x16_h5_ep33",
    "m3_mb_16x16_8x8_h5_ep33",
    "m4_mb_16x16_32x16_h5_ep33",
    "m5_mb_16x16_16x8_8x16_h5_ep33",
    "m6_mb_16x16_8x8_32x16_h5_ep33",
]

BEST_RE = re.compile(r"Best IR_RGB mINP:\s*([0-9.eE+-]+),\s*Best mAP:\s*([0-9.eE+-]+),\s*Best Rank1:\s*([0-9.eE+-]+)")
EVAL_RE = re.compile(r"mINP:\s*([0-9.eE+-]+)\s*\n\s*mAP:\s*([0-9.eE+-]+)\s*\n\s*Rank:\s*\[?\s*([0-9.eE+-]+)")
EPOCH_RE = re.compile(r"Epoch:\s*(\d+)")


def pct(value):
    if value is None:
        return ""
    value = float(value)
    if 0.0 <= value <= 1.5:
        value *= 100.0
    return f"{value:.2f}"


def load_status():
    if STATUS_PATH.is_file():
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    return {}


def patch_branches(exp_name):
    cfg = yaml.safe_load((CONFIG_DIR / f"{exp_name}.yaml").read_text(encoding="utf-8"))
    branches = cfg.get("pmt_patch_embed", {}).get("branches", [])
    return " + ".join(
        f"{branch.get('patch_size')}@{branch.get('stride_size')}"
        for branch in branches
    )


def total_epoch(exp_name):
    cfg = yaml.safe_load((CONFIG_DIR / f"{exp_name}.yaml").read_text(encoding="utf-8"))
    return cfg.get("total_train_epoch", "")


def find_log(exp_name):
    root = LOG_ROOT / exp_name
    candidates = sorted(root.glob("**/log.log")) if root.exists() else []
    if candidates:
        return candidates[-1]
    return None


def parse_log(log_path):
    if log_path is None or not log_path.is_file():
        return {}
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    current_epoch = None
    best = {"rank1": None, "map": None, "minp": None, "epoch": None}
    for line in text.splitlines():
        epoch_match = EPOCH_RE.search(line)
        if epoch_match:
            current_epoch = int(epoch_match.group(1)) + 1
        best_match = BEST_RE.search(line)
        if best_match:
            minp, map_value, rank1 = map(float, best_match.groups())
            if best["rank1"] is None or rank1 >= best["rank1"]:
                best = {"rank1": rank1, "map": map_value, "minp": minp, "epoch": current_epoch}
    final = None
    for match in EVAL_RE.finditer(text):
        minp, map_value, rank1 = map(float, match.groups())
        final = {"rank1": rank1, "map": map_value, "minp": minp}
    return {"best": best, "final": final or {}, "log": str(log_path.relative_to(ROOT))}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    status = load_status()
    rows = []
    for exp_name in EXPERIMENTS:
        parsed = parse_log(find_log(exp_name))
        best = parsed.get("best", {})
        final = parsed.get("final", {})
        state = status.get(exp_name, {}).get("status", "missing")
        rows.append(
            {
                "exp": exp_name,
                "patch_branches": patch_branches(exp_name),
                "total_train_epoch": total_epoch(exp_name),
                "best_epoch": best.get("epoch") or "",
                "Rank-1": pct(best.get("rank1")),
                "mAP": pct(best.get("map")),
                "mINP": pct(best.get("minp")),
                "final_Rank-1": pct(final.get("rank1")),
                "final_mAP": pct(final.get("map")),
                "final_mINP": pct(final.get("minp")),
                "status": state,
            }
        )

    fieldnames = [
        "exp",
        "patch_branches",
        "total_train_epoch",
        "best_epoch",
        "Rank-1",
        "mAP",
        "mINP",
        "final_Rank-1",
        "final_mAP",
        "final_mINP",
        "status",
    ]
    with RESULTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    lines = ["# MBPatch Light Ablation H5 Ep33 Results", ""]
    lines.append("| " + " | ".join(fieldnames) + " |")
    lines.append("| " + " | ".join(["---"] * len(fieldnames)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(row[name]) for name in fieldnames) + " |")
    RESULTS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(RESULTS_MD)
    print(RESULTS_CSV)


if __name__ == "__main__":
    main()
'''


OVERNIGHT_SCRIPT = r'''#!/usr/bin/env bash
set -euo pipefail

cd /home/cgv841/ybj/TVI-LFM
source /home/cgv841/anaconda3/etc/profile.d/conda.sh
conda activate clipreid

mkdir -p train_outputs/mbpatch_light_ablation_h5_ep33

python scripts/smoke_mbpatch_light_ablation_h5_ep33.py

runner_args=(
  --gpus 0,1,2,3
  --max-parallel 4
  --max-mem 2000
  --max-util 20
)
if [[ "${RERUN_FAILED:-0}" == "1" ]]; then
  runner_args+=(--rerun-failed)
fi

set +e
python scripts/run_mbpatch_light_ablation_h5_ep33.py "${runner_args[@]}"
run_rc=$?
set -e

python scripts/summarize_mbpatch_light_ablation_h5_ep33.py
exit "${run_rc}"
'''


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = OUTPUT_DIR / "backups" / timestamp
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written = make_configs(backup_root)
    written.append(patch_main_py(backup_root))
    scripts = {
        SCRIPT_DIR / "smoke_mbpatch_light_ablation_h5_ep33.py": SMOKE_SCRIPT,
        SCRIPT_DIR / "run_mbpatch_light_ablation_h5_ep33.py": RUNNER_SCRIPT,
        SCRIPT_DIR / "summarize_mbpatch_light_ablation_h5_ep33.py": SUMMARIZER_SCRIPT,
        SCRIPT_DIR / "overnight_mbpatch_light_ablation_h5_ep33.sh": OVERNIGHT_SCRIPT,
    }
    for path, content in scripts.items():
        content = textwrap.dedent(content).lstrip()
        write_text(path, content, backup_root, executable=path.suffix == ".sh")
        written.append(rel(path))
    for script in [
        MAIN_FILE,
        SCRIPT_DIR / "smoke_mbpatch_light_ablation_h5_ep33.py",
        SCRIPT_DIR / "run_mbpatch_light_ablation_h5_ep33.py",
        SCRIPT_DIR / "summarize_mbpatch_light_ablation_h5_ep33.py",
    ]:
        py_compile.compile(str(script), doraise=True)
    subprocess.run(["bash", "-n", str(SCRIPT_DIR / "overnight_mbpatch_light_ablation_h5_ep33.sh")], check=True)
    print(json.dumps({"written": written, "backup_root": str(backup_root)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
PY
  ) > "${apply_log}" 2>&1
}

run_smoke_tests() {
  local smoke_log="${LOG_DIR}/smoke_mbpatch_light_ablation.log"
  local selected_gpu
  selected_gpu="$(select_idle_gpu)"
  (
    cd "${PROJECT_ROOT}"
    printf 'Selected GPU for smoke: %s\n' "${selected_gpu}"
    CUDA_VISIBLE_DEVICES="${selected_gpu}" "${PYTHON_BIN}" scripts/smoke_mbpatch_light_ablation_h5_ep33.py
  ) > "${smoke_log}" 2>&1
}

start_overnight() {
  local start_log="${LOG_DIR}/overnight_launch.log"
  mkdir -p "${TRAIN_OUTPUT_DIR}"
  if [[ -f "${TRAIN_OUTPUT_DIR}/overnight.pid" ]]; then
    local old_pid
    old_pid="$(cat "${TRAIN_OUTPUT_DIR}/overnight.pid" 2>/dev/null || true)"
    if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
      printf 'overnight already running with pid %s\n' "${old_pid}" > "${start_log}"
      return 0
    fi
  fi
  (
    cd "${PROJECT_ROOT}"
    if [[ "${RERUN_FAILED}" == "1" ]]; then
      nohup env RERUN_FAILED=1 bash scripts/overnight_mbpatch_light_ablation_h5_ep33.sh \
        > "${TRAIN_OUTPUT_DIR}/overnight_launcher.log" 2>&1 &
    else
      nohup bash scripts/overnight_mbpatch_light_ablation_h5_ep33.sh \
        > "${TRAIN_OUTPUT_DIR}/overnight_launcher.log" 2>&1 &
    fi
    echo "$!" > "${TRAIN_OUTPUT_DIR}/overnight.pid"
    printf 'started overnight pid %s\n' "$(cat "${TRAIN_OUTPUT_DIR}/overnight.pid")"
  ) > "${start_log}" 2>&1
}

collect_state() {
  local collect_dir="${LOG_DIR}/mbpatch_state"
  rm -rf "${collect_dir}"
  mkdir -p "${collect_dir}"
  (
    cd "${PROJECT_ROOT}"
    cp -f "${TRAIN_OUTPUT_DIR}/status.json" "${collect_dir}/status.json" 2>/dev/null || true
    cp -f "${TRAIN_OUTPUT_DIR}/RESULTS.md" "${collect_dir}/RESULTS.md" 2>/dev/null || true
    cp -f "${TRAIN_OUTPUT_DIR}/results.csv" "${collect_dir}/results.csv" 2>/dev/null || true
    cp -f "${TRAIN_OUTPUT_DIR}/overnight_launcher.log" "${collect_dir}/overnight_launcher.log" 2>/dev/null || true
    cp -f "${TRAIN_OUTPUT_DIR}/overnight.pid" "${collect_dir}/overnight.pid" 2>/dev/null || true
    mkdir -p "${collect_dir}/artifacts"
    cp -r "config/stage_a/${EXP_SLUG}" "${collect_dir}/artifacts/configs" 2>/dev/null || true
    for rel in \
      "scripts/smoke_mbpatch_light_ablation_h5_ep33.py" \
      "scripts/run_mbpatch_light_ablation_h5_ep33.py" \
      "scripts/summarize_mbpatch_light_ablation_h5_ep33.py" \
      "scripts/overnight_mbpatch_light_ablation_h5_ep33.sh"; do
      if [[ -f "${rel}" ]]; then
        mkdir -p "${collect_dir}/artifacts/$(dirname "${rel}")"
        cp "${rel}" "${collect_dir}/artifacts/${rel}"
      fi
    done
    find "${TRAIN_OUTPUT_DIR}" -maxdepth 2 -type f -name launcher.log -print0 2>/dev/null |
      while IFS= read -r -d '' launcher; do
        rel="${launcher#${TRAIN_OUTPUT_DIR}/}"
        mkdir -p "${collect_dir}/launcher_logs/$(dirname "${rel}")"
        tail -n 120 "${launcher}" > "${collect_dir}/launcher_logs/${rel}.tail"
      done
    if [[ -d "logs/${EXP_SLUG}" ]]; then
      find "logs/${EXP_SLUG}" -maxdepth 6 -type f \( -name log.log -o -name test.log \) -print0 2>/dev/null |
        while IFS= read -r -d '' train_log; do
          rel="${train_log#logs/${EXP_SLUG}/}"
          mkdir -p "${collect_dir}/training_logs/$(dirname "${rel}")"
          tail -n 160 "${train_log}" > "${collect_dir}/training_logs/${rel}.tail"
        done
    fi
    nvidia-smi > "${collect_dir}/nvidia_smi.txt" 2>&1 || true
    pgrep -af "run_mbpatch_light_ablation_h5_ep33|overnight_mbpatch_light_ablation_h5_ep33|main.py --config_select .*mbpatch_light_ablation_h5_ep33" \
      > "${collect_dir}/processes.txt" 2>&1 || true
  )
}

run_summarizer() {
  local summarize_log="${LOG_DIR}/summarize_mbpatch_light_ablation.log"
  (
    cd "${PROJECT_ROOT}"
    "${PYTHON_BIN}" scripts/summarize_mbpatch_light_ablation_h5_ep33.py
  ) > "${summarize_log}" 2>&1
  collect_state
}

audit_project() {
  local audit_dir="${LOG_DIR}/audit"
  rm -rf "${audit_dir}"
  mkdir -p "${audit_dir}"
  (
    cd "${PROJECT_ROOT}"
    AUDIT_DIR="${audit_dir}" LOG_DIR="${LOG_DIR}" "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

ROOT = Path.cwd()
EXP_SLUG = "mbpatch_light_ablation_h5_ep33"
CONFIG_DIR = ROOT / "config/stage_a" / EXP_SLUG
OUTPUT_DIR = ROOT / "train_outputs" / EXP_SLUG
AUDIT_DIR = Path(os.environ["AUDIT_DIR"])
LOG_DIR = Path(os.environ["LOG_DIR"])
EXPERIMENTS = [
    "m1_mb_16x16_16x8_h5_ep33",
    "m2_mb_16x16_8x16_h5_ep33",
    "m3_mb_16x16_8x8_h5_ep33",
    "m4_mb_16x16_32x16_h5_ep33",
    "m5_mb_16x16_16x8_8x16_h5_ep33",
    "m6_mb_16x16_8x8_32x16_h5_ep33",
]
EXPECTED = {
    "total_train_epoch": 33,
    "prj_output_dim": 768,
    "sampler_type": "identity_auto_replace",
    "triplet_mining": "pmt_cross_modal_hard",
    "batch_size": 32,
    "num_pos": 4,
    "img_size": [288, 144],
}

checks = []
for exp in EXPERIMENTS:
    path = CONFIG_DIR / f"{exp}.yaml"
    checks.append({"name": f"config_exists:{exp}", "ok": path.is_file(), "detail": str(path)})
    if path.is_file():
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key, expected in EXPECTED.items():
            checks.append({
                "name": f"{exp}:{key}",
                "ok": cfg.get(key) == expected,
                "detail": f"expected={expected!r} actual={cfg.get(key)!r}",
            })
        branches = cfg.get("pmt_patch_embed", {}).get("branches", [])
        checks.append({"name": f"{exp}:patch_branches", "ok": len(branches) >= 2, "detail": str(branches)})

smoke_log = ROOT / "train_outputs" / EXP_SLUG / "overnight_launcher.log"
if not smoke_log.is_file():
    smoke_log = LOG_DIR / "smoke_mbpatch_light_ablation.log"
smoke_text = smoke_log.read_text(encoding="utf-8", errors="ignore") if smoke_log.is_file() else ""
checks.append({
    "name": "smoke_all_pass",
    "ok": "ALL MBPATCH LIGHT SMOKE TESTS PASS" in smoke_text,
    "detail": str(smoke_log),
})
status_path = OUTPUT_DIR / "status.json"
status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
checks.append({"name": "runner_status_exists", "ok": status_path.is_file(), "detail": str(status_path)})
for exp in EXPERIMENTS:
    checks.append({
        "name": f"{exp}:runner_done",
        "ok": status.get(exp, {}).get("status") == "done",
        "detail": str(status.get(exp, {})),
    })
checks.append({"name": "RESULTS.md_exists", "ok": (OUTPUT_DIR / "RESULTS.md").is_file(), "detail": str(OUTPUT_DIR / "RESULTS.md")})
checks.append({"name": "results.csv_exists", "ok": (OUTPUT_DIR / "results.csv").is_file(), "detail": str(OUTPUT_DIR / "results.csv")})

summary = {
    "ok": all(item["ok"] for item in checks),
    "checks": checks,
}
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
(AUDIT_DIR / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
lines = ["# MBPatch Light Ablation Audit", ""]
for item in checks:
    mark = "PASS" if item["ok"] else "FAIL"
    lines.append(f"- {mark} {item['name']}: {item['detail']}")
(AUDIT_DIR / "AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
raise SystemExit(0 if summary["ok"] else 1)
PY
  )
}

case "${MODE}" in
  inspect)
    write_status "running" "mbpatch inspect started" 0
    inspect_project
    write_status "succeeded" "mbpatch inspect completed" 0
    ;;
  apply)
    write_status "running" "mbpatch apply started" 0
    if apply_project_changes; then
      inspect_project
      write_status "succeeded" "mbpatch apply completed" 0
    else
      code=$?
      write_status "failed" "mbpatch apply failed; see apply log" "${code}"
      exit "${code}"
    fi
    ;;
  smoke)
    write_status "running" "mbpatch smoke started" 0
    if run_smoke_tests; then
      collect_state
      write_status "succeeded" "mbpatch smoke completed" 0
    else
      code=$?
      collect_state
      write_status "failed" "mbpatch smoke failed; see smoke log" "${code}"
      exit "${code}"
    fi
    ;;
  start)
    write_status "running" "mbpatch overnight start requested" 0
    if start_overnight; then
      collect_state
      write_status "succeeded" "mbpatch overnight started" 0
    else
      code=$?
      collect_state
      write_status "failed" "mbpatch overnight start failed" "${code}"
      exit "${code}"
    fi
    ;;
  status)
    write_status "succeeded" "mbpatch status collected" 0
    collect_state
    exit 0
    ;;
  collect)
    write_status "running" "mbpatch collect started" 0
    collect_state
    write_status "succeeded" "mbpatch collect completed" 0
    ;;
  summarize)
    write_status "running" "mbpatch summarize started" 0
    if run_summarizer; then
      write_status "succeeded" "mbpatch summarize completed" 0
    else
      code=$?
      collect_state
      write_status "failed" "mbpatch summarize failed; see summarize log" "${code}"
      exit "${code}"
    fi
    ;;
  audit)
    write_status "running" "mbpatch audit started" 0
    if audit_project; then
      collect_state
      write_status "succeeded" "mbpatch audit completed" 0
    else
      code=$?
      collect_state
      write_status "failed" "mbpatch audit failed; see audit logs" "${code}"
      exit "${code}"
    fi
    ;;
  *)
    write_status "failed" "mode ${MODE} is not implemented yet" 9
    exit 9
    ;;
esac
