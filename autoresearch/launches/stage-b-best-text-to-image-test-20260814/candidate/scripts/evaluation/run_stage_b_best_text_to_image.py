#!/usr/bin/env python3
"""Evaluate the best retained Stage-B text encoder against original RGB images."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import numpy as np


CHECKPOINT = Path(
    "/home/lab929/ybj/SALT-VI/checkpoints/stage_b/experiments/"
    "salt_ablation/r_text_visual_20260729/model_output/sysu/FV/"
    "Baseline_train[RGB_IR_Text]_joint[uni]_Blip_parameter_add_id,"
    "cross_modal_hard_Fix_Visual/models/model_Fusion_epoch_23.pth"
)
DATASET_ROOT = Path("/home/cgv841/datasets/SYSU-MM01")
TEXT_ROOT = DATASET_ROOT / "Text"
CONFIG_RELATIVE = Path("configs/stage_b/r_text_visual_20260729.yaml")


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError("missing required environment variable: {}".format(name))
    return value


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp.{}".format(os.getpid()))
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(str(temporary), str(path))


def validate_inputs(repo_root):
    config_path = repo_root / CONFIG_RELATIVE
    required = {
        "checkpoint": CHECKPOINT,
        "dataset_root": DATASET_ROOT,
        "text_root": TEXT_ROOT,
        "config": config_path,
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise RuntimeError("missing evaluation inputs: {}".format(", ".join(missing)))
    if CHECKPOINT.stat().st_size != 606796050:
        raise RuntimeError(
            "unexpected checkpoint size: {}".format(CHECKPOINT.stat().st_size)
        )
    test_ids = [
        int(value)
        for value in (DATASET_ROOT / "exp" / "test_id.txt")
        .read_text(encoding="utf-8")
        .strip()
        .split(",")
    ]
    return config_path, len(test_ids)


def parse_test_log(log_path):
    if not log_path.is_file():
        raise RuntimeError("evaluation result log was not created: {}".format(log_path))
    text = log_path.read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(
        r"Test Mode:\s*Text_RGB,\s*"
        r"mINP:\s*([-+0-9.eE]+)\s*"
        r"mAP:\s*([-+0-9.eE]+)\s*"
        r"Rank:\s*\[([^\]]+)\]",
        re.MULTILINE,
    )
    matches = pattern.findall(text)
    if not matches:
        raise RuntimeError("no Text_RGB aggregate metrics found in {}".format(log_path))
    minp_text, map_text, cmc_text = matches[-1]
    cmc = np.fromstring(cmc_text.replace("\n", " "), sep=" ")
    if cmc.size < 10:
        raise RuntimeError("Text_RGB CMC has only {} entries".format(cmc.size))
    values = {
        "Rank-1": float(cmc[0]),
        "Rank-5": float(cmc[4]),
        "Rank-10": float(cmc[9]),
        "mAP": float(map_text),
        "mINP": float(minp_text),
    }
    if not all(np.isfinite(value) for value in values.values()):
        raise RuntimeError("Text_RGB metrics contain non-finite values: {}".format(values))
    return values


def main():
    repo_root = Path(__file__).resolve().parents[2]
    config_path, test_identity_count = validate_inputs(repo_root)

    if "--validate-only" in sys.argv[1:]:
        print(
            json.dumps(
                {
                    "checkpoint": str(CHECKPOINT),
                    "checkpoint_epoch": 23,
                    "dataset_split": "SYSU-MM01 test",
                    "test_identity_count": test_identity_count,
                    "query": "legacy identity-conditioned Blip RGB caption only",
                    "gallery": "original RGB images",
                    "gallery_trials": 10,
                    "uses_ir_image_features": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    output_dir = Path(required_env("AR2_OUTPUT_DIR")).resolve()
    results_dir = Path(required_env("AR2_RESULTS_DIR")).resolve()
    physical_gpu = required_env("AR2_GPU_ID")
    evaluation_output = output_dir / "text_to_original_rgb"
    evaluation_output.mkdir(parents=True, exist_ok=True)

    settings = [
        "mode='test'",
        "test_modality='Text'",
        "test_model_type='Fusion'",
        "test_model_path='{}'".format(CHECKPOINT),
        "output_path='{}'".format(evaluation_output),
        "CUDA_VISIBLE_DEVICES='{}'".format(physical_gpu),
        "gpu_id='0'",
        "LOG4TEST=true",
        "retrieval_backend='legacy'",
        "sysu_data_path='{}'".format(DATASET_ROOT),
        "text_data_root='{}'".format(TEXT_ROOT),
        "sysu_sr_modalities=[]",
        "sysu_sr_exact_size=false",
        "seed=0",
        "test_mode='all'",
        "gall_mode='single'",
    ]
    command = [
        sys.executable,
        str(repo_root / "scripts" / "train.py"),
        "--config_select",
        str(config_path),
    ]
    for setting in settings:
        command.extend(["--set", setting])

    completed = subprocess.run(command, cwd=str(repo_root), check=False)
    if completed.returncode != 0:
        return completed.returncode

    values = parse_test_log(evaluation_output / "logs" / "test.log")
    payload = {
        "primary_metric": values["Rank-1"],
        "metrics": {
            **values,
            "checkpoint_epoch": 23.0,
            "gallery_trials": 10.0,
            "selected_gpu": float(physical_gpu),
            "test_identity_count": float(test_identity_count),
        },
        "protocol": {
            "dataset": "SYSU-MM01 test split",
            "query": "legacy identity-conditioned Blip RGB caption only",
            "gallery": "original RGB images",
            "search": "all-search single-shot 10-trial aggregate",
            "uses_ir_image_features": False,
        },
        "checkpoint": str(CHECKPOINT),
    }
    atomic_write_json(results_dir / "metrics.json", payload)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("Stage-B text-to-image evaluation failed: {}".format(exc), file=sys.stderr)
        sys.exit(1)
