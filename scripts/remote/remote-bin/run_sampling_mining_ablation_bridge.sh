#!/usr/bin/env bash
set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${BIN_DIR}/researchops_common.sh"
SCRIPT_NAME="run_sampling_mining_ablation_bridge.sh"

EXPERIMENT_ID=""
PROJECT_ROOT="${DEFAULT_PROJECT_ROOT}"
PYTHON_BIN="${DEFAULT_PYTHON_BIN}"
DATA_ROOT="${DEFAULT_DATA_ROOT}"
PRETRAIN="${DEFAULT_PRETRAIN}"
GPU="${DEFAULT_GPU}"
MODE="inspect"
MAX_PARALLEL="4"
MAX_MEM="2000"
MAX_UTIL="20"
GPUS=""
RERUN_FAILED=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --experiment-id) EXPERIMENT_ID="${2:-}"; shift 2 ;;
    --project-root) PROJECT_ROOT="${2:-}"; shift 2 ;;
    --python) PYTHON_BIN="${2:-}"; shift 2 ;;
    --data-root) DATA_ROOT="${2:-}"; shift 2 ;;
    --pretrained) PRETRAIN="${2:-}"; shift 2 ;;
    --gpu) GPU="${2:-}"; shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --max-parallel) MAX_PARALLEL="${2:-}"; shift 2 ;;
    --max-mem) MAX_MEM="${2:-}"; shift 2 ;;
    --max-util) MAX_UTIL="${2:-}"; shift 2 ;;
    --gpus) GPUS="${2:-}"; shift 2 ;;
    --rerun-failed) RERUN_FAILED=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "${EXPERIMENT_ID}" ]] || die "--experiment-id is required"
validate_experiment_id "${EXPERIMENT_ID}"
ensure_under_remote_root "${PROJECT_ROOT}"
require_dir "${PROJECT_ROOT}" "project root"
require_executable "${PYTHON_BIN}" "python"

case "${MODE}" in
  inspect|apply|smoke|overnight|apply-smoke|summarize|status|collect|archive|commit|audit|cleanup|push) ;;
  *) die "--mode must be inspect, apply, smoke, apply-smoke, overnight, summarize, status, collect, archive, commit, audit, cleanup, or push" ;;
esac

EXP_ROOT="$(experiment_root "${EXPERIMENT_ID}")"
RESULTS_DIR="${EXP_ROOT}/results"
LOG_DIR="${RESULTS_DIR}/logs"
STATUS_FILE="${EXP_ROOT}/status.json"
mkdir -p "${LOG_DIR}"

write_bridge_status() {
  local state="$1"
  local message="$2"
  local exit_code="${3:-0}"
  MODE="${MODE}" write_status "${STATUS_FILE}" "${state}" "${message}" "${exit_code}" >/dev/null
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
    printf 'gpu=%s\n' "${GPU}" >> "${inspect_dir}/bridge_env.txt"
    git status --short > "${inspect_dir}/git_status.txt" 2>&1 || true
    git rev-parse --abbrev-ref HEAD > "${inspect_dir}/git_branch.txt" 2>&1 || true
    git rev-parse HEAD > "${inspect_dir}/git_head.txt" 2>&1 || true

    local rel
    for rel in \
      config/default.yaml \
      config/stage_a/pmt_vit_stage_a_pmt_recipe_288x144_768.yaml \
      config/stage_a/pmt_vit_stage_a_current_best.yaml \
      docs/stage_a_results.md \
      README.md \
      data_loader/sampler.py \
      data_loader/loader.py \
      tools/loss.py \
      tools/__init__.py \
      core/build.py \
      core/train.py \
      main.py; do
      if [[ -f "${rel}" ]]; then
        mkdir -p "${inspect_dir}/$(dirname "${rel}")"
        cp "${rel}" "${inspect_dir}/${rel}"
      else
        printf 'missing: %s\n' "${rel}" >> "${inspect_dir}/missing_files.txt"
      fi
    done

    "${PYTHON_BIN}" - <<'PY' > "${inspect_dir}/symbol_scan.txt"
from pathlib import Path

needles = [
    "IdentitySampler",
    "TripletLoss_WRT",
    "PMTTripletLoss",
    "_forward_pmt_recipe",
    "pmt_triplet_margin",
    "pmt_recipe",
]
for rel in ["data_loader/sampler.py", "data_loader/loader.py", "tools/loss.py", "core/build.py"]:
    p = Path(rel)
    if not p.exists():
        continue
    print(f"## {rel}")
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if any(needle in line for needle in needles):
            print(f"{i}: {line}")
PY
  )
}

run_repo_command() {
  local log_file="$1"
  shift
  (
    cd "${PROJECT_ROOT}"
    "$@"
  ) > "${log_file}" 2>&1
}

apply_project_changes() {
  local apply_log="${LOG_DIR}/apply_sampling_mining_ablation.log"
  PROJECT_ROOT="${PROJECT_ROOT}" \
  RESULTS_DIR="${RESULTS_DIR}" \
  DATA_ROOT="${DATA_ROOT}" \
  PRETRAIN="${PRETRAIN}" \
  "${PYTHON_BIN}" - <<'PY' > "${apply_log}" 2>&1
import copy
import json
import os
import re
import shutil
import textwrap
from datetime import datetime
from pathlib import Path

import yaml

root = Path(os.environ["PROJECT_ROOT"]).resolve()
results_dir = Path(os.environ["RESULTS_DIR"]).resolve()
pretrain = os.environ.get("PRETRAIN", "")
backup_root = results_dir / "logs" / "backups" / datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
changed = []


def path_for(rel):
    path = (root / rel).resolve()
    if root not in path.parents and path != root:
        raise RuntimeError(f"path escaped project root: {rel}")
    return path


def read_text(rel):
    return path_for(rel).read_text(encoding="utf-8")


def write_text(rel, text):
    path = path_for(rel)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == text:
        return False
    if path.exists():
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    changed.append(rel)
    return True


def replace_once(text, old, new, rel, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def append_default_fields():
    rel = "config/default.yaml"
    text = read_text(rel)
    additions = [
        ("sampler_type", "sampler_type: identity_current_replace"),
        ("triplet_mining", "triplet_mining: pmt_hard"),
        ("pmt_cross_modal_triplet_weight", "pmt_cross_modal_triplet_weight: 1.0"),
    ]
    for key, line in additions:
        if not re.search(rf"(?m)^\s*{re.escape(key)}\s*:", text):
            if not text.endswith("\n"):
                text += "\n"
            text += line + "\n"
    write_text(rel, text)


def patch_sampler():
    rel = "data_loader/sampler.py"
    text = read_text(rel)
    if "class AutoReplaceIdentitySampler" in text:
        return
    marker = """    def __len__(self):
        return self.N

'''
"""
    addition = """    def __len__(self):
        return self.N


class AutoReplaceIdentitySampler(Sampler):
    \"\"\"Identity sampler that replaces only when an ID has too few samples.\"\"\"

    def __init__(self, train_color_label, train_thermal_label, color_pos, thermal_pos, num_pos, batchSize):
        uni_label = np.unique(train_color_label)
        self.n_classes = len(uni_label)

        N = np.maximum(len(train_color_label), len(train_thermal_label))
        index1 = []
        index2 = []
        for _ in range(int(N / (batchSize * num_pos)) + 1):
            batch_idx = np.random.choice(uni_label, batchSize, replace=False)
            for label in batch_idx:
                color_pool = color_pos[label]
                thermal_pool = thermal_pos[label]
                sample_color = np.random.choice(
                    color_pool, num_pos, replace=len(color_pool) < num_pos
                )
                sample_thermal = np.random.choice(
                    thermal_pool, num_pos, replace=len(thermal_pool) < num_pos
                )
                index1.extend(sample_color)
                index2.extend(sample_thermal)

        self.index1 = np.asarray(index1)
        self.index2 = np.asarray(index2)
        self.N = N

    def __iter__(self):
        return iter(np.arange(len(self.index1)))

    def __len__(self):
        return self.N

'''
"""
    text = replace_once(text, marker, addition, rel, "IdentitySampler insertion point")
    write_text(rel, text)


def patch_loader():
    rel = "data_loader/loader.py"
    text = read_text(rel)
    text = re.sub(
        r"(?m)^from data_loader\.sampler import .*$",
        "from data_loader.sampler import GenIdx, IdentitySampler, AutoReplaceIdentitySampler",
        text,
        count=1,
    )
    old_num_pos = "        self.num_pos = config.num_pos\n"
    new_num_pos = (
        "        self.num_pos = config.num_pos\n"
        "        self.sampler_type = getattr(config, \"sampler_type\", \"identity_current_replace\")\n"
    )
    if "self.sampler_type" not in text:
        text = replace_once(text, old_num_pos, new_num_pos, rel, "num_pos block")
    old = """    def get_train_loader(self):
        sampler = IdentitySampler(self.samples.train_color_label, self.samples.train_thermal_label, self.color_pos,
                                  self.thermal_pos, self.num_pos, int(self.batch_size / self.num_pos))
        self.samples.cIndex = sampler.index1
        self.samples.tIndex = sampler.index2
        train_loader = data.DataLoader(self.samples, batch_size=self.batch_size,
                                       sampler=sampler, num_workers=self.num_workers, drop_last=True)
        return train_loader
"""
    new = """    def get_train_loader(self):
        if self.sampler_type == \"identity_current_replace\":
            sampler_cls = IdentitySampler
        elif self.sampler_type == \"identity_auto_replace\":
            sampler_cls = AutoReplaceIdentitySampler
        else:
            raise ValueError(f\"Unsupported sampler_type: {self.sampler_type}\")

        sampler = sampler_cls(self.samples.train_color_label, self.samples.train_thermal_label, self.color_pos,
                              self.thermal_pos, self.num_pos, int(self.batch_size / self.num_pos))
        self.samples.cIndex = sampler.index1
        self.samples.tIndex = sampler.index2
        train_loader = data.DataLoader(self.samples, batch_size=self.batch_size,
                                       sampler=sampler, num_workers=self.num_workers, drop_last=True)
        return train_loader
"""
    if "sampler_cls = AutoReplaceIdentitySampler" not in text:
        text = replace_once(text, old, new, rel, "get_train_loader block")
    write_text(rel, text)


def patch_loss():
    rel = "tools/loss.py"
    text = read_text(rel)
    if "class CrossModalPMTTripletLoss" in text:
        return
    marker = "\n\nclass PMTMSEL(nn.Module):\n"
    addition = r'''

class CrossModalPMTTripletLoss(nn.Module):
    def __init__(self, margin=0.1, feat_norm="no"):
        super(CrossModalPMTTripletLoss, self).__init__()
        self.margin = margin
        self.feat_norm = feat_norm
        if margin >= 0:
            self.ranking_loss = nn.MarginRankingLoss(margin=margin)
        else:
            self.ranking_loss = nn.SoftMarginLoss()

    def _directional_loss(self, dist_mat, anchor_labels, other_labels):
        is_pos = anchor_labels.view(-1, 1).eq(other_labels.view(1, -1))
        is_neg = anchor_labels.view(-1, 1).ne(other_labels.view(1, -1))
        valid = is_pos.any(dim=1) & is_neg.any(dim=1)
        if not torch.any(valid):
            return dist_mat.sum() * 0.0

        pos_dist = dist_mat.masked_fill(~is_pos, -float("inf"))
        neg_dist = dist_mat.masked_fill(~is_neg, float("inf"))
        dist_ap = pos_dist.max(dim=1)[0][valid]
        dist_an = neg_dist.min(dim=1)[0][valid]
        y = dist_an.new_ones(dist_an.size())
        if self.margin >= 0:
            return self.ranking_loss(dist_an, dist_ap, y)
        return self.ranking_loss(dist_an - dist_ap, y)

    def forward(self, visible_feats, ir_feats, labels):
        if visible_feats.size(0) != ir_feats.size(0):
            raise ValueError("visible_feats and ir_feats must have the same batch size")
        labels = labels.view(-1)
        if labels.size(0) != visible_feats.size(0):
            raise ValueError("labels must match the per-modality batch size")
        if self.feat_norm == "yes":
            visible_feats = F.normalize(visible_feats, p=2, dim=-1)
            ir_feats = F.normalize(ir_feats, p=2, dim=-1)

        dist_v2i = pdist_torch(visible_feats, ir_feats)
        loss_v2i = self._directional_loss(dist_v2i, labels, labels)
        loss_i2v = self._directional_loss(dist_v2i.t(), labels, labels)
        return (loss_v2i + loss_i2v) / 2

'''
    text = replace_once(text, marker, addition + "class PMTMSEL(nn.Module):\n", rel, "PMTMSEL marker")
    write_text(rel, text)


def patch_build():
    rel = "core/build.py"
    text = read_text(rel)
    text = text.replace(
        "    PMTTripletLoss,\n    PMTMSEL,",
        "    PMTTripletLoss,\n    CrossModalPMTTripletLoss,\n    PMTMSEL,",
    )
    criterion_marker = """        self.pmt_tri_criterion = PMTTripletLoss(
            margin=getattr(args, "pmt_triplet_margin", 0.1),
            feat_norm="no",
        )
        self.pmt_msel_criterion = PMTMSEL(getattr(args, "num_pos", 4), feat_norm="no")
"""
    criterion_new = """        self.pmt_tri_criterion = PMTTripletLoss(
            margin=getattr(args, "pmt_triplet_margin", 0.1),
            feat_norm="no",
        )
        self.cross_modal_tri_criterion = CrossModalPMTTripletLoss(
            margin=getattr(args, "pmt_triplet_margin", 0.1),
            feat_norm="no",
        )
        self.pmt_msel_criterion = PMTMSEL(getattr(args, "num_pos", 4), feat_norm="no")
"""
    if "self.cross_modal_tri_criterion" not in text:
        text = replace_once(text, criterion_marker, criterion_new, rel, "PMT criterion block")

    old = """        if is_gray_stage:
            tri_loss = (
                self.pmt_tri_criterion(visible_feats, visible_feats, label_rgb)
                + self.pmt_tri_criterion(ir_feats, ir_feats, label_ir)
            )
            zero = features.new_zeros(())
            ret.update({"tri_loss": tri_loss})
            ret.update({"msel_loss": zero})
            ret.update({"dcl_loss": zero})
        else:
            tri_loss = self.pmt_tri_criterion(features, features, labels)
            msel_loss = self.pmt_msel_criterion(features, labels) * getattr(self.args, "pmt_msel_weight", 0.5)
            dcl_loss = self.pmt_dcl_criterion(features, labels) * getattr(self.args, "pmt_dcl_weight", 0.5)
            ret.update({"tri_loss": tri_loss})
            ret.update({"msel_loss": msel_loss})
            ret.update({"dcl_loss": dcl_loss})
"""
    new = """        triplet_mining = getattr(self.args, "triplet_mining", "pmt_hard")
        if triplet_mining not in {"pmt_hard", "wrt", "pmt_cross_modal_hard"}:
            raise ValueError(f"Unsupported triplet_mining: {triplet_mining}")

        if is_gray_stage:
            if triplet_mining == "wrt":
                tri_loss = (
                    self.tri_criterion(visible_feats, label_rgb)
                    + self.tri_criterion(ir_feats, label_ir)
                )
            else:
                tri_loss = (
                    self.pmt_tri_criterion(visible_feats, visible_feats, label_rgb)
                    + self.pmt_tri_criterion(ir_feats, ir_feats, label_ir)
                )
            zero = features.new_zeros(())
            ret.update({"tri_loss": tri_loss})
            ret.update({"msel_loss": zero})
            ret.update({"dcl_loss": zero})
        else:
            if triplet_mining == "pmt_hard":
                tri_loss = self.pmt_tri_criterion(features, features, labels)
            elif triplet_mining == "wrt":
                tri_loss = self.tri_criterion(features, labels)
            else:
                tri_loss = self.cross_modal_tri_criterion(visible_feats, ir_feats, label_rgb)
                tri_loss = tri_loss * getattr(self.args, "pmt_cross_modal_triplet_weight", 1.0)
            msel_loss = self.pmt_msel_criterion(features, labels) * getattr(self.args, "pmt_msel_weight", 0.5)
            dcl_loss = self.pmt_dcl_criterion(features, labels) * getattr(self.args, "pmt_dcl_weight", 0.5)
            ret.update({"tri_loss": tri_loss})
            ret.update({"msel_loss": msel_loss})
            ret.update({"dcl_loss": dcl_loss})
        ret.update({"triplet_mining": triplet_mining})
"""
    if "triplet_mining = getattr(self.args" not in text:
        text = replace_once(text, old, new, rel, "PMT triplet branch")
    write_text(rel, text)


def generate_configs():
    base_rel = "config/stage_a/pmt_vit_stage_a_pmt_recipe_288x144_768.yaml"
    base_path = path_for(base_rel)
    with base_path.open("r", encoding="utf-8") as f:
        base = yaml.load(f, Loader=yaml.FullLoader) or {}
    if not isinstance(base, dict):
        raise RuntimeError(f"{base_rel} must be a YAML mapping")

    specs = [
        ("s0_pk8x4_current_replace_hard.yaml", "s0_pk8x4_current_replace_hard", "identity_current_replace", "pmt_hard", 32, 4),
        ("s1_pk8x4_auto_replace_hard.yaml", "s1_pk8x4_auto_replace_hard", "identity_auto_replace", "pmt_hard", 32, 4),
        ("s2_pk16x2_auto_replace_hard.yaml", "s2_pk16x2_auto_replace_hard", "identity_auto_replace", "pmt_hard", 32, 2),
        ("s3_pk4x8_auto_replace_hard.yaml", "s3_pk4x8_auto_replace_hard", "identity_auto_replace", "pmt_hard", 32, 8),
        ("h1_pk8x4_auto_replace_wrt.yaml", "h1_pk8x4_auto_replace_wrt", "identity_auto_replace", "wrt", 32, 4),
        ("h5_pk8x4_auto_replace_crossmodal_hard.yaml", "h5_pk8x4_auto_replace_crossmodal_hard", "identity_auto_replace", "pmt_cross_modal_hard", 32, 4),
    ]
    out_dir = path_for("config/stage_a/sampling_mining_ablation")
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, exp, sampler_type, triplet_mining, batch_size, num_pos in specs:
        cfg = copy.deepcopy(base)
        cfg.update({
            "output_path": f"logs/sampling_mining_ablation/{exp}/",
            "sampler_type": sampler_type,
            "triplet_mining": triplet_mining,
            "batch_size": batch_size,
            "num_pos": num_pos,
            "pmt_triplet_margin": 0.1,
        })
        if "pmt_cross_modal_triplet_weight" not in cfg:
            cfg["pmt_cross_modal_triplet_weight"] = 1.0
        text = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
        write_text(str(Path("config/stage_a/sampling_mining_ablation") / filename), text)


SMOKE_SCRIPT = r'''#!/usr/bin/env python
import gc
import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import torch

from core import build_model
from data_loader.loader import Loader
from tools.utils import load_train_configs


CONFIGS = [
    "config/stage_a/sampling_mining_ablation/s0_pk8x4_current_replace_hard.yaml",
    "config/stage_a/sampling_mining_ablation/s1_pk8x4_auto_replace_hard.yaml",
    "config/stage_a/sampling_mining_ablation/s2_pk16x2_auto_replace_hard.yaml",
    "config/stage_a/sampling_mining_ablation/s3_pk4x8_auto_replace_hard.yaml",
    "config/stage_a/sampling_mining_ablation/h1_pk8x4_auto_replace_wrt.yaml",
    "config/stage_a/sampling_mining_ablation/h5_pk8x4_auto_replace_crossmodal_hard.yaml",
]


def set_pid_num(config):
    if config.dataset == "sysu":
        config.pid_num = 395
    elif config.dataset == "regdb":
        config.pid_num = 206
    elif config.dataset == "llcm":
        config.pid_num = 713
    else:
        raise ValueError(f"Unsupported dataset: {config.dataset}")


def assert_chunk_layout(labels, num_pos, name):
    if labels.numel() % num_pos != 0:
        raise AssertionError(f"{name} length {labels.numel()} is not divisible by num_pos={num_pos}")
    chunks = labels.view(-1, num_pos)
    if not torch.all(chunks.eq(chunks[:, :1])):
        raise AssertionError(f"{name} does not have one identity per consecutive num_pos chunk")


def move_batch(batch, device):
    return {key: value.to(device) for key, value in batch.items()}


def smoke_one(config_path):
    config = load_train_configs(config_path)
    set_pid_num(config)
    config.gpu_id = "0"
    config.CUDA_VISIBLE_DEVICES = os.environ.get("CUDA_VISIBLE_DEVICES", "0")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"[SMOKE] {Path(config_path).name} sampler={getattr(config, 'sampler_type', None)} mining={getattr(config, 'triplet_mining', None)} device={device}")

    loaders = Loader(config)
    train_loader = loaders.get_train_loader()
    batch = next(iter(train_loader))

    target_rgb = batch["target_rgb"].long()
    target_ir = batch["target_ir"].long()
    if target_rgb.shape != target_ir.shape:
        raise AssertionError(f"target_rgb shape {tuple(target_rgb.shape)} != target_ir shape {tuple(target_ir.shape)}")
    if bool(getattr(config, "pmt_recipe", False)) and not torch.equal(target_rgb, target_ir):
        raise AssertionError("PMT recipe requires target_rgb == target_ir")
    assert_chunk_layout(target_rgb, int(config.num_pos), "target_rgb")
    assert_chunk_layout(target_ir, int(config.num_pos), "target_ir")

    model = build_model(config).to(device)
    model.set_train()
    batch = move_batch(batch, device)
    rgb_stage_epoch = int(getattr(config, "pmt_progressive_epoch", 6))
    ret = model(batch, mode=None, current_epoch=rgb_stage_epoch)

    required = ["id_loss", "tri_loss", "msel_loss", "dcl_loss"]
    for key in required:
        if key not in ret:
            raise AssertionError(f"missing loss: {key}")
        value = ret[key]
        if not torch.is_tensor(value):
            raise AssertionError(f"{key} is not a tensor")
        if not torch.isfinite(value.detach()).all():
            raise AssertionError(f"{key} is not finite: {value}")

    total_loss = sum(value for key, value in ret.items() if "loss" in key)
    if not torch.isfinite(total_loss.detach()).all():
        raise AssertionError(f"total_loss is not finite: {total_loss}")
    total_loss.backward()
    print(f"[PASS] {Path(config_path).name}")

    del model, loaders, train_loader, batch, ret, total_loss
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def main():
    for config_path in CONFIGS:
        try:
            smoke_one(config_path)
        except Exception:
            print(f"[FAIL] {Path(config_path).name}")
            traceback.print_exc()
            return 1
    print("[ALL PASS] sampling/mining ablation smoke tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


RUNNER_SCRIPT = r'''#!/usr/bin/env python
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml


CONFIGS = [
    "config/stage_a/sampling_mining_ablation/s0_pk8x4_current_replace_hard.yaml",
    "config/stage_a/sampling_mining_ablation/s1_pk8x4_auto_replace_hard.yaml",
    "config/stage_a/sampling_mining_ablation/s2_pk16x2_auto_replace_hard.yaml",
    "config/stage_a/sampling_mining_ablation/s3_pk4x8_auto_replace_hard.yaml",
    "config/stage_a/sampling_mining_ablation/h1_pk8x4_auto_replace_wrt.yaml",
    "config/stage_a/sampling_mining_ablation/h5_pk8x4_auto_replace_crossmodal_hard.yaml",
]
OUT_ROOT = Path("train_outputs/sampling_mining_ablation")
STATUS_PATH = OUT_ROOT / "status.json"


def now():
    return datetime.now().isoformat(timespec="seconds")


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.load(f, Loader=yaml.FullLoader) or {}


def exp_name(config_path):
    return Path(config_path).stem


def read_status():
    if STATUS_PATH.exists():
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    return {}


def write_status(status):
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATUS_PATH)


def max_logged_epoch(output_path):
    root = Path(output_path)
    epochs = []
    for log_path in list(root.rglob("log.log")) + list(root.rglob("train.log")):
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r"Epoch:\s*(\d+)", text):
            epochs.append(int(match.group(1)))
    return max(epochs) if epochs else None


def is_done_by_log(config_path):
    cfg = load_yaml(config_path)
    total = int(cfg.get("total_train_epoch", 0))
    output_path = cfg.get("output_path", "")
    if not total or not output_path:
        return False
    epoch = max_logged_epoch(output_path)
    return epoch is not None and epoch + 1 >= total


def query_gpus(selected, max_mem, max_util):
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    output = subprocess.check_output(cmd, text=True)
    allowed = None
    if selected:
        allowed = {int(item) for item in selected.split(",") if item.strip()}
    gpus = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        idx = int(float(parts[0]))
        mem = int(float(parts[1]))
        util = 0 if parts[2].upper() == "N/A" else int(float(parts[2]))
        if allowed is not None and idx not in allowed:
            continue
        if mem < max_mem and util < max_util:
            gpus.append(idx)
    return gpus


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--gpus", default="")
    parser.add_argument("--rerun-failed", action="store_true")
    parser.add_argument("--max-mem", type=int, default=2000)
    parser.add_argument("--max-util", type=int, default=20)
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()

    status = read_status()
    queue = []
    for cfg_path in CONFIGS:
        name = exp_name(cfg_path)
        entry = status.get(name, {"config": cfg_path, "status": "pending"})
        entry["config"] = cfg_path
        if entry.get("status") == "done" or is_done_by_log(cfg_path):
            entry["status"] = "done"
            status[name] = entry
            continue
        if entry.get("status") == "failed" and not args.rerun_failed:
            status[name] = entry
            continue
        entry.update({"status": "pending", "return_code": None})
        status[name] = entry
        queue.append(cfg_path)
    write_status(status)

    running = {}
    while queue or running:
        for name, proc_info in list(running.items()):
            proc = proc_info["proc"]
            rc = proc.poll()
            if rc is None:
                continue
            proc_info["log_handle"].close()
            entry = status[name]
            entry["end_time"] = now()
            entry["return_code"] = rc
            entry["status"] = "done" if rc == 0 else "failed"
            status[name] = entry
            del running[name]
            write_status(status)

        used_gpus = {info["gpu"] for info in running.values()}
        while queue and len(running) < args.max_parallel:
            free_gpus = [gpu for gpu in query_gpus(args.gpus, args.max_mem, args.max_util) if gpu not in used_gpus]
            if not free_gpus:
                break
            gpu = free_gpus[0]
            cfg_path = queue.pop(0)
            name = exp_name(cfg_path)
            log_dir = OUT_ROOT / name
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "launcher.log"
            runtime_config = log_dir / "config_for_gpu.yaml"
            cfg_data = load_yaml(cfg_path)
            cfg_data["CUDA_VISIBLE_DEVICES"] = str(gpu)
            cfg_data["gpu_id"] = "0"
            runtime_config.write_text(yaml.safe_dump(cfg_data, sort_keys=False, allow_unicode=True), encoding="utf-8")
            log_handle = log_path.open("ab")
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = str(gpu)
            cmd = [sys.executable, "main.py", "--config_select", str(runtime_config)]
            proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT, env=env)
            status[name] = {
                "config": cfg_path,
                "runtime_config": str(runtime_config),
                "status": "running",
                "gpu": gpu,
                "start_time": now(),
                "end_time": None,
                "return_code": None,
                "command": "CUDA_VISIBLE_DEVICES={} {}".format(gpu, " ".join(cmd)),
            }
            running[name] = {"proc": proc, "gpu": gpu, "log_handle": log_handle}
            used_gpus.add(gpu)
            write_status(status)

        if queue or running:
            time.sleep(args.poll_seconds)

    return 1 if any(item.get("status") == "failed" for item in status.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


SUMMARY_SCRIPT = r'''#!/usr/bin/env python
import csv
import json
import re
from pathlib import Path

import yaml


CONFIG_DIR = Path("config/stage_a/sampling_mining_ablation")
LOG_ROOT = Path("logs/sampling_mining_ablation")
OUT_ROOT = Path("train_outputs/sampling_mining_ablation")
STATUS_PATH = OUT_ROOT / "status.json"


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.load(f, Loader=yaml.FullLoader) or {}


def first_float(text):
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
    return float(match.group(0)) if match else None


def parse_log(log_path):
    text = log_path.read_text(encoding="utf-8", errors="replace")
    current_epoch = None
    best = {"best_epoch": "", "Rank-1": "", "mAP": "", "mINP": ""}
    final = {"final_Rank-1": "", "final_mAP": "", "final_mINP": "", "final_epoch": ""}
    for line in text.splitlines():
        epoch_match = re.search(r"Epoch:\s*(\d+)", line)
        if epoch_match:
            current_epoch = int(epoch_match.group(1))
            final["final_epoch"] = current_epoch
        best_match = re.search(r"Best .*?mINP:\s*([^,]+),\s*Best mAP:\s*([^,]+),\s*Best Rank1:\s*([^,\s]+)", line)
        if best_match:
            best["best_epoch"] = current_epoch if current_epoch is not None else ""
            best["mINP"] = first_float(best_match.group(1))
            best["mAP"] = first_float(best_match.group(2))
            best["Rank-1"] = first_float(best_match.group(3))

    metric_blocks = re.finditer(
        r"mINP:\s*([^\n]+)\s*\nmAP:\s*([^\n]+)\s*\n\s*Rank:\s*\[?([^\]\n\s,]+)",
        text,
        flags=re.MULTILINE,
    )
    for match in metric_blocks:
        final["final_mINP"] = first_float(match.group(1))
        final["final_mAP"] = first_float(match.group(2))
        final["final_Rank-1"] = first_float(match.group(3))
    return {**best, **final}


def find_log(exp):
    root = LOG_ROOT / exp
    candidates = list(root.rglob("log.log")) + list(root.rglob("train.log"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    status = {}
    if STATUS_PATH.exists():
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    rows = []
    for cfg_path in sorted(CONFIG_DIR.glob("*.yaml")):
        cfg = load_yaml(cfg_path)
        exp = cfg_path.stem
        log_path = find_log(exp)
        metrics = {}
        if log_path:
            metrics = parse_log(log_path)
        run_status = status.get(exp, {}).get("status", "unknown")
        if not log_path:
            run_status = "missing_log" if run_status == "unknown" else run_status
        rows.append({
            "exp": exp,
            "sampler_type": cfg.get("sampler_type", ""),
            "triplet_mining": cfg.get("triplet_mining", ""),
            "batch_size": cfg.get("batch_size", ""),
            "num_pos": cfg.get("num_pos", ""),
            "best_epoch": metrics.get("best_epoch", ""),
            "Rank-1": metrics.get("Rank-1", ""),
            "mAP": metrics.get("mAP", ""),
            "mINP": metrics.get("mINP", ""),
            "final_Rank-1": metrics.get("final_Rank-1", ""),
            "final_mAP": metrics.get("final_mAP", ""),
            "final_mINP": metrics.get("final_mINP", ""),
            "status": run_status,
        })

    fields = ["exp", "sampler_type", "triplet_mining", "batch_size", "num_pos", "best_epoch", "Rank-1", "mAP", "mINP", "final_Rank-1", "final_mAP", "final_mINP", "status"]
    with (OUT_ROOT / "results.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    lines = ["| " + " | ".join(fields) + " |", "|" + "|".join(["---"] * len(fields)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(field, "")) for field in fields) + " |")
    (OUT_ROOT / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_ROOT / 'RESULTS.md'} and {OUT_ROOT / 'results.csv'}")


if __name__ == "__main__":
    main()
'''


OVERNIGHT_SCRIPT = r'''#!/usr/bin/env bash
set -euo pipefail

cd /home/cgv841/ybj/TVI-LFM
source /home/cgv841/anaconda3/etc/profile.d/conda.sh
conda activate clipreid

mkdir -p train_outputs/sampling_mining_ablation

select_idle_gpu() {
  python - <<'SMOKEPY'
import subprocess

out = subprocess.check_output([
    "nvidia-smi",
    "--query-gpu=index,memory.used,utilization.gpu",
    "--format=csv,noheader,nounits",
], text=True)
best = None
for line in out.splitlines():
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 3:
        continue
    idx = int(float(parts[0]))
    mem = int(float(parts[1]))
    util = 0 if parts[2].upper() == "N/A" else int(float(parts[2]))
    if mem < 2000 and util < 20:
        item = (mem, util, idx)
        if best is None or item < best:
            best = item
if best is not None:
    print(best[2])
SMOKEPY
}

SMOKE_GPU=""
while [[ -z "${SMOKE_GPU}" ]]; do
  SMOKE_GPU="$(select_idle_gpu || true)"
  if [[ -z "${SMOKE_GPU}" ]]; then
    echo "No idle GPU for smoke; waiting 60s..."
    sleep 60
  fi
done
echo "Running smoke on physical GPU ${SMOKE_GPU}"
CUDA_VISIBLE_DEVICES="${SMOKE_GPU}" python scripts/smoke_sampling_mining_ablation.py

python scripts/run_sampling_mining_ablation.py \
  --gpus 0,1,2,3 \
  --max-parallel 4 \
  --max-mem 2000 \
  --max-util 20

python scripts/summarize_sampling_mining_ablation.py
'''


def write_generated_scripts():
    scripts = {
        "scripts/smoke_sampling_mining_ablation.py": SMOKE_SCRIPT,
        "scripts/run_sampling_mining_ablation.py": RUNNER_SCRIPT,
        "scripts/summarize_sampling_mining_ablation.py": SUMMARY_SCRIPT,
        "scripts/overnight_sampling_mining_ablation.sh": OVERNIGHT_SCRIPT,
    }
    for rel, content in scripts.items():
        if rel.endswith(".sh"):
            content = content if content.endswith("\n") else content + "\n"
        write_text(rel, content)
        if rel.endswith(".sh"):
            path_for(rel).chmod(0o755)


def compile_changed_python():
    import py_compile

    for rel in [
        "data_loader/sampler.py",
        "data_loader/loader.py",
        "tools/loss.py",
        "core/build.py",
        "scripts/smoke_sampling_mining_ablation.py",
        "scripts/run_sampling_mining_ablation.py",
        "scripts/summarize_sampling_mining_ablation.py",
    ]:
        py_compile.compile(str(path_for(rel)), doraise=True)


append_default_fields()
patch_sampler()
patch_loader()
patch_loss()
patch_build()
generate_configs()
write_generated_scripts()
compile_changed_python()

print(json.dumps({"changed": changed, "backup_root": str(backup_root)}, ensure_ascii=False, indent=2))
PY
}

run_smoke_tests() {
  local smoke_log="${LOG_DIR}/smoke_sampling_mining_ablation.log"
  local selected_gpu
  selected_gpu="$(resolve_gpu "${GPU}")"
  (
    cd "${PROJECT_ROOT}"
    export CUDA_VISIBLE_DEVICES="${selected_gpu}"
    "${PYTHON_BIN}" scripts/smoke_sampling_mining_ablation.py
  ) > "${smoke_log}" 2>&1
}

run_summary() {
  local summary_log="${LOG_DIR}/summarize_sampling_mining_ablation.log"
  run_repo_command "${summary_log}" "${PYTHON_BIN}" scripts/summarize_sampling_mining_ablation.py
}

archive_sampling_mining_results() {
  local archive_log="${LOG_DIR}/archive_sampling_mining_ablation.log"
  PROJECT_ROOT="${PROJECT_ROOT}" \
  RESULTS_DIR="${RESULTS_DIR}" \
  "${PYTHON_BIN}" - <<'PY' > "${archive_log}" 2>&1
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml

root = Path(os.environ["PROJECT_ROOT"]).resolve()
results_dir = Path(os.environ["RESULTS_DIR"]).resolve()
backup_root = results_dir / "logs" / "backups" / (datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "_archive")
changed = []


def path_for(rel):
    path = (root / rel).resolve()
    if root not in path.parents and path != root:
        raise RuntimeError(f"path escaped project root: {rel}")
    return path


def read_text(rel):
    return path_for(rel).read_text(encoding="utf-8")


def write_text(rel, text):
    path = path_for(rel)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == text:
        return False
    if path.exists():
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    changed.append(rel)
    return True


def load_yaml(rel):
    with path_for(rel).open("r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=yaml.FullLoader) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{rel} must be a YAML mapping")
    return data


def write_yaml(rel, data):
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    write_text(rel, text)


def update_current_best_config():
    h5_rel = "config/stage_a/sampling_mining_ablation/h5_pk8x4_auto_replace_crossmodal_hard.yaml"
    base_rel = "config/stage_a/pmt_vit_stage_a_pmt_recipe_288x144_768.yaml"
    source_rel = h5_rel if path_for(h5_rel).exists() else base_rel
    cfg = load_yaml(source_rel)
    cfg.update({
        "output_path": "logs/stage_a_pmt_vit_current_best/",
        "sampler_type": "identity_auto_replace",
        "triplet_mining": "pmt_cross_modal_hard",
        "batch_size": 32,
        "num_pos": 4,
        "pmt_triplet_margin": 0.1,
    })
    cfg.setdefault("pmt_cross_modal_triplet_weight", 1.0)
    write_yaml("config/stage_a/pmt_vit_stage_a_current_best.yaml", cfg)


SECTION_TITLE = "## Sampling and Mining Ablation Result"
SECTION = """## Sampling and Mining Ablation Result

Experiment id: `sampling_mining_ablation_20260706`

All six sampling/mining ablation runs completed successfully. The selected
current-best run is `h5_pk8x4_auto_replace_crossmodal_hard`.

Current best metrics:

| Metric | Value |
|---|---:|
| Rank-1 | 67.09% |
| mAP | 65.08% |
| mINP | 52.00% |

The Stage A main configuration is updated from
`identity_current_replace + PK=8x4 + pmt_hard` to
`identity_auto_replace + PK=8x4 + pmt_cross_modal_hard`.

Current main configuration:

```yaml
sampler_type: identity_auto_replace
triplet_mining: pmt_cross_modal_hard
batch_size: 32
num_pos: 4
pmt_triplet_margin: 0.1
```

The stable Stage A backbone and training settings remain unchanged:
`PMT_VIT + PMT recipe + 288x144 + prj_output_dim=768`, AdamW,
`lr_visual=0.0003`, cosine scheduler, `warmup_epochs=3`,
`target_lr_factor=0.01`, `total_train_epoch=24`, `eval_start_epoch=2`,
`eval_epoch=2`, and `seed=0`.

| Run | Rank-1 | mAP | mINP | Label | Decision |
|---|---:|---:|---:|---|---|
| `s0_pk8x4_current_replace_hard` | 65.53 | 64.11 | 51.65 | old baseline / historical baseline | Keep as historical baseline only; do not use as default. |
| `s1_pk8x4_auto_replace_hard` | 66.43 | 64.58 | 51.63 | sampler baseline | Keep as sampler baseline; use `identity_auto_replace`, but not plain `pmt_hard`, as main. |
| `s2_pk16x2_auto_replace_hard` | 65.31 | 64.34 | 52.09 | negative / secondary result | Keep as secondary control; do not select PK=16x2 as default. |
| `s3_pk4x8_auto_replace_hard` | 66.54 | 63.65 | 50.34 | not selected | Keep as record only; do not select PK=4x8 as default. |
| `h1_pk8x4_auto_replace_wrt` | 64.03 | 62.30 | 49.02 | failed / not suitable | Keep as failed control; do not use WRT as default mining. |
| `h5_pk8x4_auto_replace_crossmodal_hard` | 67.09 | 65.08 | 52.00 | current best / selected main config | Select as current main configuration. |
"""


def replace_or_append_section(text):
    if SECTION_TITLE not in text:
        return text.rstrip() + "\n\n" + SECTION.rstrip() + "\n"
    pattern = re.compile(rf"(?ms)^{re.escape(SECTION_TITLE)}\n.*?(?=^## |\Z)")
    return pattern.sub(SECTION.rstrip() + "\n", text.rstrip()) + "\n"


def update_stage_a_results_doc():
    preferred = [
        "docs/stage_a_results.md",
        "docs/stage-a-results.md",
        "docs/experiments/stage_a_results.md",
        "reports/stage_a_results.md",
    ]
    target = None
    for rel in preferred:
        if path_for(rel).exists():
            target = rel
            break
    if target is None:
        target = "docs/stage_a_results.md"
        text = "# Stage A Results\n"
    else:
        text = read_text(target)
    write_text(target, replace_or_append_section(text))


README_BLOCK_TITLE = "## Current Stage A Main Config"
README_BLOCK = """## Current Stage A Main Config

The selected Stage A main config is:

```text
config/stage_a/pmt_vit_stage_a_current_best.yaml
```

It corresponds to `PMT_VIT + PMT recipe + 288x144 + 768 no-projection +
identity_auto_replace + PK=8x4 + pmt_cross_modal_hard`.

The historical PMT recipe baseline is retained for comparison at:

```text
config/stage_a/pmt_vit_stage_a_pmt_recipe_288x144_768.yaml
```
"""


def update_readme_pointer():
    rel = "README.md"
    path = path_for(rel)
    if not path.exists():
        return
    text = read_text(rel)
    if README_BLOCK_TITLE in text:
        pattern = re.compile(rf"(?ms)^{re.escape(README_BLOCK_TITLE)}\n.*?(?=^## |\Z)")
        text = pattern.sub(README_BLOCK.rstrip() + "\n", text.rstrip()) + "\n"
    else:
        text = text.rstrip() + "\n\n" + README_BLOCK.rstrip() + "\n"
    write_text(rel, text)


update_current_best_config()
update_stage_a_results_doc()
update_readme_pointer()

summary = {
    "changed": changed,
    "backup_root": str(backup_root),
    "current_best_config": "config/stage_a/pmt_vit_stage_a_current_best.yaml",
    "selected": "h5_pk8x4_auto_replace_crossmodal_hard",
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
}

commit_sampling_mining_results() {
  local commit_log="${LOG_DIR}/commit_sampling_mining_ablation.log"
  (
    cd "${PROJECT_ROOT}"
    printf 'Project root: %s\n' "${PROJECT_ROOT}"
    printf 'Git top-level: '
    git rev-parse --show-toplevel
    printf '\nBranch before commit: '
    git rev-parse --abbrev-ref HEAD
    printf 'HEAD before commit: '
    git rev-parse HEAD
    printf '\nStatus before scoped add:\n'
    git status --short

    if [[ -n "$(git diff --cached --name-only)" ]]; then
      printf '\nPre-existing staged changes detected; validating final staged scope before commit.\n'
      git diff --cached --name-status
    fi

    required_paths=(
      README.md
      config/default.yaml
      config/stage_a/pmt_vit_stage_a_current_best.yaml
      core/build.py
      data_loader/loader.py
      data_loader/sampler.py
      docs/stage_a_results.md
      tools/loss.py
    )
    optional_paths=(
      config/stage_a/sampling_mining_ablation
      scripts/overnight_sampling_mining_ablation.sh
      scripts/run_sampling_mining_ablation.py
      scripts/smoke_sampling_mining_ablation.py
      scripts/summarize_sampling_mining_ablation.py
    )

    missing=0
    for rel in "${required_paths[@]}"; do
      if [[ ! -e "${rel}" ]]; then
        printf 'Missing required commit path: %s\n' "${rel}" >&2
        missing=1
      fi
    done
    [[ "${missing}" -eq 0 ]] || exit 4

    git add -- "${required_paths[@]}"
    for rel in "${optional_paths[@]}"; do
      if [[ -e "${rel}" ]]; then
        git add -- "${rel}"
      else
        printf 'Optional commit path absent, skipping: %s\n' "${rel}"
      fi
    done

    printf '\nScoped staged changes:\n'
    git diff --cached --name-status --relative -- .

    staged_relative="$(git diff --cached --name-only --relative -- .)"
    if [[ -z "${staged_relative}" ]]; then
      printf '\nNo scoped changes to commit.\n'
      exit 0
    fi

    all_staged_count="$(git diff --cached --name-only | sed '/^$/d' | wc -l | tr -d ' ')"
    scoped_staged_count="$(printf '%s\n' "${staged_relative}" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [[ "${all_staged_count}" != "${scoped_staged_count}" ]]; then
      printf '\nRefusing to commit because staged changes outside TVI-LFM are present:\n' >&2
      git diff --cached --name-status >&2
      exit 6
    fi

    bad_paths="$(
      printf '%s\n' "${staged_relative}" |
        grep -Ev '^(README\.md|config/default\.yaml|config/stage_a/pmt_vit_stage_a_current_best\.yaml|config/stage_a/sampling_mining_ablation/.*|core/build\.py|data_loader/loader\.py|data_loader/sampler\.py|docs/stage_a_results\.md|scripts/(overnight_sampling_mining_ablation\.sh|run_sampling_mining_ablation\.py|smoke_sampling_mining_ablation\.py|summarize_sampling_mining_ablation\.py)|tools/loss\.py)$' || true
    )"
    if [[ -n "${bad_paths}" ]]; then
      printf '\nRefusing to commit unexpected staged paths:\n%s\n' "${bad_paths}" >&2
      exit 5
    fi

    git -c user.name="${GIT_AUTHOR_NAME:-Codex}" \
      -c user.email="${GIT_AUTHOR_EMAIL:-codex@localhost}" \
      commit -m "Archive sampling mining ablation current best"

    printf '\nHEAD after commit: '
    git rev-parse HEAD
    printf '\nStatus after commit:\n'
    git status --short
  ) > "${commit_log}" 2>&1
}

audit_workspace_redundancy() {
  local audit_dir="${LOG_DIR}/workspace_audit"
  rm -rf "${audit_dir}"
  mkdir -p "${audit_dir}"
  (
    set +e
    printf 'remote_root=%s\n' "${REMOTE_ROOT}" > "${audit_dir}/summary.txt"
    printf 'project_root=%s\n' "${PROJECT_ROOT}" >> "${audit_dir}/summary.txt"
    printf 'generated_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${audit_dir}/summary.txt"

    printf '# Top-level size under REMOTE_ROOT\n' > "${audit_dir}/top_level_du.txt"
    timeout 120 du -shx "${REMOTE_ROOT}"/* "${REMOTE_ROOT}"/.[!.]* 2>/dev/null |
      sort -h >> "${audit_dir}/top_level_du.txt"

    printf '# Candidate path sizes\n' > "${audit_dir}/candidate_du.txt"
    for rel in \
      bin \
      experiments \
      non_research \
      PMT-SYSU \
      Single-experiment \
      TVI-LFM \
      TVI-LFM/logs \
      TVI-LFM/logs/sampling_mining_ablation \
      TVI-LFM/train_outputs \
      TVI-LFM/train_outputs/sampling_mining_ablation \
      TVI-LFM/config/stage_a/sampling_mining_ablation \
      TVI-LFM/docs \
      LASTVIT_RETIREMENT_CHECKLIST_2026-07-06.md; do
      if [[ -e "${REMOTE_ROOT}/${rel}" ]]; then
        du -shx "${REMOTE_ROOT}/${rel}" 2>/dev/null
      else
        printf 'missing\t%s\n' "${REMOTE_ROOT}/${rel}"
      fi
    done >> "${audit_dir}/candidate_du.txt"

    printf '# Important subdirectory sizes\n' > "${audit_dir}/important_subdir_du.txt"
    for pattern in \
      "${REMOTE_ROOT}/PMT-SYSU/outputs"/* \
      "${REMOTE_ROOT}/PMT-SYSU/outputs"/*/* \
      "${REMOTE_ROOT}/TVI-LFM/logs"/* \
      "${REMOTE_ROOT}/Single-experiment/logs"/*; do
      if [[ -e "${pattern}" ]]; then
        du -shx "${pattern}" 2>/dev/null
      fi
    done | sort -h >> "${audit_dir}/important_subdir_du.txt"

    printf '# Largest files under REMOTE_ROOT, same filesystem\n' > "${audit_dir}/large_files_top200.tsv"
    timeout 180 find "${REMOTE_ROOT}" -xdev -type f -printf '%s\t%p\n' 2>/dev/null |
      sort -rn |
      head -200 >> "${audit_dir}/large_files_top200.tsv"

    printf '# Python caches and bytecode\n' > "${audit_dir}/python_cache_candidates.txt"
    timeout 120 find "${REMOTE_ROOT}" -xdev \( -type d -name __pycache__ -o -type f -name '*.pyc' \) -print 2>/dev/null |
      head -500 >> "${audit_dir}/python_cache_candidates.txt"

    printf '# Sampling/mining generated outputs\n' > "${audit_dir}/sampling_mining_outputs.txt"
    timeout 120 find "${REMOTE_ROOT}" -xdev \( \
        -path '*/sampling_mining_ablation*' -o \
        -name 'run_sampling_mining_ablation.py' -o \
        -name 'smoke_sampling_mining_ablation.py' -o \
        -name 'summarize_sampling_mining_ablation.py' -o \
        -name 'overnight_sampling_mining_ablation.sh' \
      \) -print 2>/dev/null |
      sort >> "${audit_dir}/sampling_mining_outputs.txt"

    printf '# Git status from REMOTE_ROOT\n' > "${audit_dir}/workspace_git_status.txt"
    (
      cd "${REMOTE_ROOT}" && git status --short
    ) >> "${audit_dir}/workspace_git_status.txt" 2>&1

    printf '# Git status from PROJECT_ROOT\n' > "${audit_dir}/tvilfm_git_status.txt"
    (
      cd "${PROJECT_ROOT}" && git status --short
    ) >> "${audit_dir}/tvilfm_git_status.txt" 2>&1

    printf '# Recent TVI-LFM commits\n' > "${audit_dir}/recent_commits.txt"
    (
      cd "${PROJECT_ROOT}" && git log --oneline --decorate -n 8
    ) >> "${audit_dir}/recent_commits.txt" 2>&1

    cat > "${audit_dir}/redundancy_notes.md" <<'EOF'
# Workspace Redundancy Audit Notes

This is a read-only audit. Nothing has been deleted or moved.

Interpretation guide:

- `TVI-LFM/train_outputs/sampling_mining_ablation/`: generated runner state,
  launch logs, runtime configs, and summarized ablation outputs. It is often
  redundant after results are fetched and committed, but keep it if exact
  server-side run provenance is still needed.
- `TVI-LFM/logs/sampling_mining_ablation/`: training logs and model output
  directory for the six runs. Do not delete until checkpoints/logs are no
  longer needed.
- `${REMOTE_ROOT}/experiments/`: remote experiment result archive managed by
  the fixed entrypoints. Usually safe to prune only after local fetch and
  explicit confirmation.
- `${REMOTE_ROOT}/bin/`: deployed fixed entrypoints. Not redundant while this
  automation is in use.
- Python `__pycache__` / `*.pyc`: generally disposable, but only clean with a
  dedicated confirmed cleanup command.
- Git-untracked files outside `TVI-LFM` may belong to other work and should not
  be removed by this audit.
EOF
  )
}

cleanup_non_tvilfm_redundancy() {
  local cleanup_dir="${LOG_DIR}/workspace_cleanup"
  rm -rf "${cleanup_dir}"
  mkdir -p "${cleanup_dir}"
  REMOTE_ROOT="${REMOTE_ROOT}" \
  PROJECT_ROOT="${PROJECT_ROOT}" \
  CLEANUP_DIR="${cleanup_dir}" \
  "${PYTHON_BIN}" - <<'PY'
import json
import os
import shutil
from pathlib import Path

remote_root = Path(os.environ["REMOTE_ROOT"]).resolve()
tvilfm_root = Path(os.environ["PROJECT_ROOT"]).resolve()
cleanup_dir = Path(os.environ["CLEANUP_DIR"]).resolve()

targets = {}
records = []


def is_under(path, parent):
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


def add_target(kind, path):
    path = Path(path)
    try:
        resolved = path.resolve()
    except FileNotFoundError:
        return
    if not resolved.exists():
        return
    if not is_under(resolved, remote_root):
        raise RuntimeError(f"refusing path outside REMOTE_ROOT: {resolved}")
    if is_under(resolved, tvilfm_root):
        raise RuntimeError(f"refusing to touch TVI-LFM path: {resolved}")
    targets[str(resolved)] = {"kind": kind, "path": resolved}


def path_size(path):
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for filename in filenames:
            fp = Path(dirpath) / filename
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total


def human_size(size):
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024


# Python caches outside TVI-LFM only.
for dirpath, dirnames, filenames in os.walk(remote_root):
    current = Path(dirpath).resolve()
    kept_dirs = []
    for dirname in dirnames:
        child = (current / dirname).resolve()
        if is_under(child, tvilfm_root) or dirname == ".git":
            continue
        if dirname == "__pycache__":
            add_target("python_cache_dir", child)
            continue
        kept_dirs.append(dirname)
    dirnames[:] = kept_dirs
    for filename in filenames:
        if filename.endswith(".pyc"):
            add_target("python_pyc_file", current / filename)


pmt_outputs = remote_root / "PMT-SYSU" / "outputs" / "pmt_sysu"
if pmt_outputs.exists():
    for child in pmt_outputs.iterdir():
        if child.is_dir() and "smoke" in child.name:
            if child.parent.resolve() != pmt_outputs.resolve():
                raise RuntimeError(f"unexpected smoke parent: {child}")
            add_target("pmt_sysu_smoke_dir", child)

    for run_name in ("official_reproduction", "mbpatch_reproduction"):
        checkpoint_dir = pmt_outputs / run_name / "checkpoints"
        if checkpoint_dir.exists():
            for checkpoint in checkpoint_dir.glob("epoch_*.pth"):
                if checkpoint.parent.resolve() != checkpoint_dir.resolve():
                    raise RuntimeError(f"unexpected checkpoint parent: {checkpoint}")
                add_target("pmt_sysu_intermediate_epoch_checkpoint", checkpoint)


total_bytes = 0
for item in sorted(targets.values(), key=lambda x: str(x["path"])):
    path = item["path"]
    size = path_size(path)
    total_bytes += size
    record = {
        "kind": item["kind"],
        "path": str(path),
        "bytes": size,
        "size": human_size(size),
        "status": "pending",
    }
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        record["status"] = "deleted"
    except FileNotFoundError:
        record["status"] = "already_missing"
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = repr(exc)
    records.append(record)

failed = [item for item in records if item["status"] == "failed"]
summary = {
    "remote_root": str(remote_root),
    "tvilfm_root_skipped": str(tvilfm_root),
    "target_count": len(records),
    "failed_count": len(failed),
    "planned_bytes": total_bytes,
    "planned_size": human_size(total_bytes),
    "policy": [
        "skip all paths under TVI-LFM",
        "delete Python caches outside TVI-LFM",
        "delete PMT-SYSU pmt_sysu/*smoke* directories",
        "delete epoch_*.pth under official_reproduction and mbpatch_reproduction checkpoints",
        "keep best.pth and latest.pth",
    ],
}

cleanup_dir.mkdir(parents=True, exist_ok=True)
(cleanup_dir / "cleanup_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
(cleanup_dir / "cleanup_records.json").write_text(
    json.dumps(records, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
with (cleanup_dir / "cleanup_records.tsv").open("w", encoding="utf-8") as f:
    f.write("status\tkind\tbytes\tsize\tpath\n")
    for record in records:
        f.write(
            f"{record['status']}\t{record['kind']}\t{record['bytes']}\t{record['size']}\t{record['path']}\n"
        )

print(json.dumps(summary, ensure_ascii=False, indent=2))
if failed:
    raise SystemExit(1)
PY
}

push_sampling_mining_commit() {
  local push_log="${LOG_DIR}/push_sampling_mining_ablation.log"
  (
    cd "${PROJECT_ROOT}"
    printf 'Project root: %s\n' "${PROJECT_ROOT}"
    printf 'Git top-level: '
    git rev-parse --show-toplevel
    branch="$(git rev-parse --abbrev-ref HEAD)"
    if [[ "${branch}" == "HEAD" ]]; then
      printf 'Refusing to push from detached HEAD.\n' >&2
      exit 3
    fi
    printf 'Branch: %s\n' "${branch}"
    printf 'HEAD before push: '
    git rev-parse HEAD
    printf '\nRecent commits before push:\n'
    git log --oneline --decorate -n 5
    printf '\nRemote configuration:\n'
    git remote -v
    proxy_env="${REMOTE_ROOT}/non_research/codex_proxy/proxy-env.sh"
    if [[ -f "${proxy_env}" ]]; then
      printf '\nLoading proxy env: %s\n' "${proxy_env}"
      set +u
      # shellcheck disable=SC1090
      source "${proxy_env}"
      set -u
      printf 'Proxy env after load:\n'
      env | grep -Ei '^(http_proxy|https_proxy|all_proxy|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY)=' || true
    else
      printf '\nNo proxy env found at %s; pushing without proxy env.\n' "${proxy_env}"
    fi
    proxy_url="${HTTPS_PROXY:-${https_proxy:-http://127.0.0.1:7897}}"
    export HTTPS_PROXY="${HTTPS_PROXY:-${proxy_url}}"
    export HTTP_PROXY="${HTTP_PROXY:-${proxy_url}}"
    export https_proxy="${https_proxy:-${proxy_url}}"
    export http_proxy="${http_proxy:-${proxy_url}}"
    printf 'Git HTTPS proxy: %s\n' "${proxy_url}"
    printf '\nStatus before push:\n'
    git status --short
    printf '\nCommits ahead of origin/%s:\n' "${branch}"
    git log --oneline "origin/${branch}..HEAD" 2>/dev/null || true
    printf '\nRunning: git push origin %s\n' "${branch}"
    push_ok=0
    if git -c http.proxy="${proxy_url}" -c https.proxy="${proxy_url}" push origin "${branch}"; then
      push_ok=1
    else
      printf '\nHTTPS git push failed; trying SSH fallbacks with BatchMode.\n' >&2
      ssh_base_cmd='ssh -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new'
      ssh_targets=(
        "git@github.com:westriver-moon/REID.git"
        "ssh://git@ssh.github.com:443/westriver-moon/REID.git"
      )
      ssh_commands=("${ssh_base_cmd}")
      if command -v nc >/dev/null 2>&1; then
        ssh_commands+=("${ssh_base_cmd} -o ProxyCommand='nc -X connect -x 127.0.0.1:7897 %h %p'")
      else
        printf '\nNo nc command found; skipping SSH-over-HTTP-proxy fallback.\n' >&2
      fi
      for ssh_cmd in "${ssh_commands[@]}"; do
        for ssh_target in "${ssh_targets[@]}"; do
          printf '\nRunning: GIT_SSH_COMMAND=%s git push %s %s\n' "${ssh_cmd}" "${ssh_target}" "${branch}"
          if GIT_SSH_COMMAND="${ssh_cmd}" git push "${ssh_target}" "${branch}"; then
            push_ok=1
            break 2
          fi
        done
      done
    fi
    if [[ "${push_ok}" -ne 1 ]]; then
      printf '\ngit push failed for HTTPS and SSH fallbacks.\n' >&2
      exit 7
    fi
    printf '\nHEAD after push: '
    local_head="$(git rev-parse HEAD)"
    printf '%s\n' "${local_head}"
    printf '\nRemote HEAD after push:\n'
    remote_line="$(git -c http.proxy="${proxy_url}" -c https.proxy="${proxy_url}" ls-remote origin "refs/heads/${branch}")"
    printf '%s\n' "${remote_line}"
    remote_head="$(printf '%s\n' "${remote_line}" | awk '{print $1}')"
    if [[ "${remote_head}" != "${local_head}" ]]; then
      printf 'Remote head mismatch after push: local=%s remote=%s\n' "${local_head}" "${remote_head}" >&2
      exit 8
    fi
  ) > "${push_log}" 2>&1
}

start_overnight() {
  local overnight_dir="${PROJECT_ROOT}/train_outputs/sampling_mining_ablation"
  mkdir -p "${overnight_dir}"
  if [[ -f "${overnight_dir}/overnight.pid" ]]; then
    local old_pid
    old_pid="$(cat "${overnight_dir}/overnight.pid" 2>/dev/null || true)"
    if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
      printf 'overnight already running with pid %s\n' "${old_pid}" > "${LOG_DIR}/overnight_launch.log"
      return 0
    fi
  fi
  if pgrep -af "scripts/run_sampling_mining_ablation.py" >/dev/null 2>&1; then
    pgrep -af "scripts/run_sampling_mining_ablation.py" > "${LOG_DIR}/overnight_launch.log" || true
    return 0
  fi
  (
    cd "${PROJECT_ROOT}"
    nohup bash scripts/overnight_sampling_mining_ablation.sh \
      > "${overnight_dir}/overnight_launcher.log" 2>&1 &
    echo "$!" > "${overnight_dir}/overnight.pid"
  )
}

collect_runner_state() {
  local collect_dir="${LOG_DIR}/runner"
  local out_dir="${PROJECT_ROOT}/train_outputs/sampling_mining_ablation"
  rm -rf "${collect_dir}"
  mkdir -p "${collect_dir}"
  (
    cd "${PROJECT_ROOT}"
    if [[ -d "${out_dir}" ]]; then
      cp -f "${out_dir}/status.json" "${collect_dir}/runner_status.json" 2>/dev/null || true
      cp -f "${out_dir}/overnight_launcher.log" "${collect_dir}/overnight_launcher.log" 2>/dev/null || true
      cp -f "${out_dir}/overnight.pid" "${collect_dir}/overnight.pid" 2>/dev/null || true
      cp -f "${out_dir}/RESULTS.md" "${RESULTS_DIR}/RESULTS.md" 2>/dev/null || true
      cp -f "${out_dir}/results.csv" "${RESULTS_DIR}/results.csv" 2>/dev/null || true
      cp -f "${out_dir}/RESULTS.md" "${collect_dir}/RESULTS.md" 2>/dev/null || true
      cp -f "${out_dir}/results.csv" "${collect_dir}/results.csv" 2>/dev/null || true
      find "${out_dir}" -maxdepth 2 -type f -name launcher.log -print0 2>/dev/null |
        while IFS= read -r -d '' log_file; do
          rel="${log_file#${out_dir}/}"
          mkdir -p "${collect_dir}/$(dirname "${rel}")"
          tail -n 80 "${log_file}" > "${collect_dir}/${rel}.tail"
        done
    fi
    nvidia-smi > "${collect_dir}/nvidia_smi.txt" 2>&1 || true
    pgrep -af "overnight_sampling_mining_ablation|run_sampling_mining_ablation.py|main.py --config_select .*sampling_mining_ablation" \
      > "${collect_dir}/processes.txt" 2>&1 || true
    find logs/sampling_mining_ablation -maxdepth 5 -type f \( -name log.log -o -name train.log \) -print \
      > "${collect_dir}/training_logs.txt" 2>/dev/null || true
    find logs/sampling_mining_ablation -maxdepth 7 -type f \( -name log.log -o -name train.log \) -print0 2>/dev/null |
      while IFS= read -r -d '' train_log; do
        rel="${train_log#logs/sampling_mining_ablation/}"
        mkdir -p "${collect_dir}/training_log_tails/$(dirname "${rel}")"
        tail -n 120 "${train_log}" > "${collect_dir}/training_log_tails/${rel}.tail"
      done
  )
}

case "${MODE}" in
  inspect)
    write_bridge_status "running" "sampling/mining bridge inspect started" 0
    inspect_project
    write_bridge_status "succeeded" "sampling/mining bridge inspect completed" 0
    ;;
  status)
    collect_runner_state
    cat "${STATUS_FILE}"
    exit 0
    ;;
  apply)
    write_bridge_status "running" "sampling/mining apply started" 0
    if apply_project_changes; then
      inspect_project
      write_bridge_status "succeeded" "sampling/mining apply completed" 0
    else
      code=$?
      write_bridge_status "failed" "sampling/mining apply failed; see apply log" "${code}"
      exit "${code}"
    fi
    ;;
  smoke)
    write_bridge_status "running" "sampling/mining smoke started" 0
    if run_smoke_tests; then
      write_bridge_status "succeeded" "sampling/mining smoke completed" 0
    else
      code=$?
      write_bridge_status "failed" "sampling/mining smoke failed; see smoke log" "${code}"
      exit "${code}"
    fi
    ;;
  apply-smoke)
    write_bridge_status "running" "sampling/mining apply-smoke started" 0
    if ! apply_project_changes; then
      code=$?
      write_bridge_status "failed" "sampling/mining apply failed; see apply log" "${code}"
      exit "${code}"
    fi
    inspect_project
    if run_smoke_tests; then
      write_bridge_status "succeeded" "sampling/mining apply-smoke completed" 0
    else
      code=$?
      write_bridge_status "failed" "sampling/mining smoke failed; see smoke log" "${code}"
      exit "${code}"
    fi
    ;;
  summarize)
    write_bridge_status "running" "sampling/mining summarize started" 0
    if run_summary; then
      write_bridge_status "succeeded" "sampling/mining summarize completed" 0
    else
      code=$?
      write_bridge_status "failed" "sampling/mining summarize failed; see summary log" "${code}"
      exit "${code}"
    fi
    ;;
  archive)
    write_bridge_status "running" "sampling/mining archive started" 0
    if archive_sampling_mining_results; then
      inspect_project
      collect_runner_state
      write_bridge_status "succeeded" "sampling/mining archive completed" 0
    else
      code=$?
      write_bridge_status "failed" "sampling/mining archive failed; see archive log" "${code}"
      exit "${code}"
    fi
    ;;
  commit)
    write_bridge_status "running" "sampling/mining commit started" 0
    if commit_sampling_mining_results; then
      inspect_project
      collect_runner_state
      write_bridge_status "succeeded" "sampling/mining commit completed" 0
    else
      code=$?
      write_bridge_status "failed" "sampling/mining commit failed; see commit log" "${code}"
      exit "${code}"
    fi
    ;;
  audit)
    write_bridge_status "running" "workspace redundancy audit started" 0
    if audit_workspace_redundancy; then
      write_bridge_status "succeeded" "workspace redundancy audit completed" 0
    else
      code=$?
      write_bridge_status "failed" "workspace redundancy audit failed; see workspace_audit logs" "${code}"
      exit "${code}"
    fi
    ;;
  cleanup)
    write_bridge_status "running" "non-TVI-LFM redundancy cleanup started" 0
    if cleanup_non_tvilfm_redundancy; then
      audit_workspace_redundancy
      write_bridge_status "succeeded" "non-TVI-LFM redundancy cleanup completed" 0
    else
      code=$?
      audit_workspace_redundancy || true
      write_bridge_status "failed" "non-TVI-LFM redundancy cleanup failed; see workspace_cleanup logs" "${code}"
      exit "${code}"
    fi
    ;;
  push)
    write_bridge_status "running" "sampling/mining push started" 0
    if push_sampling_mining_commit; then
      inspect_project
      collect_runner_state
      write_bridge_status "succeeded" "sampling/mining push completed" 0
    else
      code=$?
      write_bridge_status "failed" "sampling/mining push failed; see push log" "${code}"
      exit "${code}"
    fi
    ;;
  collect)
    write_bridge_status "running" "sampling/mining collect started" 0
    collect_runner_state
    write_bridge_status "succeeded" "sampling/mining collect completed" 0
    ;;
  overnight)
    write_bridge_status "running" "sampling/mining overnight launch started" 0
    start_overnight
    write_bridge_status "submitted" "sampling/mining overnight launched with nohup" 0
    ;;
esac

cat "${STATUS_FILE}"
