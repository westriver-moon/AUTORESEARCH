#!/usr/bin/env python3
"""Run the 70-epoch PMT-ViT Stage-A no-MBPatch batch-128 comparison."""

import json
import math
import os
from pathlib import Path
import subprocess
import sys


EXPERIMENT_ID = "SALTVI-STAGEA-PMT-NOMB-B128-FLASH-70EP-20260814"
TOTAL_EPOCHS = 70
CONFIG_BATCH_SIZE = 64
NUM_POS = 4


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


def metric_payload(rank1, map_value, minp, epoch):
    return {
        "primary_metric": rank1,
        "metrics": {
            "Rank-1": rank1,
            "mAP": map_value,
            "mINP": minp,
            "best_epoch": float(epoch),
        },
    }


def best_jsonl_eval(events_path):
    if not events_path.is_file():
        return None
    best = None
    with events_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "invalid JSONL at {}:{}: {}".format(events_path, line_number, exc)
                )
            if event.get("event_type") != "eval_epoch":
                continue
            metrics = event.get("metrics") or {}
            try:
                rank1 = float(metrics["Rank-1"])
                map_value = float(metrics["mAP"])
                minp = float(metrics["mINP"])
                epoch = int(event.get("epoch", -1))
            except (KeyError, TypeError, ValueError):
                continue
            if not all(math.isfinite(value) for value in (rank1, map_value, minp)):
                continue
            payload = metric_payload(rank1, map_value, minp, epoch)
            if best is None or rank1 > best[0]:
                best = (rank1, payload)
    return None if best is None else best[1]


def best_tensorboard_eval(output_dir):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    event_files = sorted(
        output_dir.glob("model_output/**/vis_logs/performance/events.out.tfevents.*")
    )
    if not event_files:
        return None
    best = None
    for event_file in event_files:
        accumulator = EventAccumulator(
            str(event_file), size_guidance={"scalars": 0}
        )
        accumulator.Reload()
        scalar_tags = set(accumulator.Tags().get("scalars", []))
        required_tags = {"R1_IR", "mAP", "mINP"}
        if not required_tags.issubset(scalar_tags):
            continue
        by_tag = {
            tag: {int(event.step): float(event.value) for event in accumulator.Scalars(tag)}
            for tag in required_tags
        }
        common_steps = set(by_tag["R1_IR"]) & set(by_tag["mAP"]) & set(by_tag["mINP"])
        for epoch in common_steps:
            rank1 = by_tag["R1_IR"][epoch]
            map_value = by_tag["mAP"][epoch]
            minp = by_tag["mINP"][epoch]
            if not all(math.isfinite(value) for value in (rank1, map_value, minp)):
                continue
            payload = metric_payload(rank1, map_value, minp, epoch)
            if best is None or rank1 > best[0]:
                best = (rank1, payload)
    return None if best is None else best[1]


def best_eval_result(events_path, output_dir):
    payload = best_jsonl_eval(events_path)
    if payload is not None:
        return payload
    payload = best_tensorboard_eval(output_dir)
    if payload is not None:
        return payload
    raise RuntimeError(
        "no finite aggregate evaluation metrics found in {} or TensorBoard performance events"
        .format(output_dir)
    )


def validate_inputs(repo_root, config_path):
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    from salt_vi.config.validation import validate_runtime_config
    from salt_vi.utils.utils import load_train_configs

    config = validate_runtime_config(load_train_configs(str(config_path)))
    expected = {
        "pretrain_choice": "PMT_VIT",
        "pmt_recipe": True,
        "joint_mode": "image_only",
        "training_mode": "RGB_IR",
        "batch_size": CONFIG_BATCH_SIZE,
        "num_pos": NUM_POS,
        "total_train_epoch": TOTAL_EPOCHS,
        "pmt_attention_backend": "flash",
        "pmt_gradient_checkpointing": True,
        "seed": 0,
    }
    mismatches = {
        name: {"expected": value, "actual": getattr(config, name, None)}
        for name, value in expected.items()
        if getattr(config, name, None) != value
    }
    identities_per_batch = int(config.batch_size) // int(config.num_pos)
    if identities_per_batch != 16:
        mismatches["identities_per_batch"] = {
            "expected": 16,
            "actual": identities_per_batch,
        }
    if set(config.sysu_sr_modalities) != {"rgb", "ir"}:
        mismatches["sysu_sr_modalities"] = {
            "expected": ["rgb", "ir"],
            "actual": list(config.sysu_sr_modalities),
        }
    if mismatches:
        raise RuntimeError("invalid experiment configuration: {}".format(mismatches))

    required_paths = {
        "pmt_pretrained": Path(config.pmt_pretrained),
        "sysu_data_path": Path(config.sysu_data_path),
        "sysu_sr_data_root": Path(config.sysu_sr_data_root),
        "sysu_sr_view_manifest": Path(config.sysu_sr_view_manifest),
    }
    missing = [name for name, path in required_paths.items() if not path.exists()]
    if missing:
        raise RuntimeError("missing Stage-A inputs: {}".format(", ".join(missing)))

    return {
        "config_batch_size_per_modality": int(config.batch_size),
        "num_pos_per_modality": int(config.num_pos),
        "identities_per_batch": identities_per_batch,
        "effective_cross_modal_images": int(config.batch_size) * 2,
        "attention_backend": config.pmt_attention_backend,
        "planned_epochs": int(config.total_train_epoch),
        "required_paths": {name: str(path) for name, path in required_paths.items()},
    }


def main():
    repo_root = Path(__file__).resolve().parents[2]
    config_path = (
        repo_root
        / "configs"
        / "stage_a"
        / "reproduction"
        / "source_core"
        / "stage_a_current_best_no_mbpatch_pasd_rgb_ir_geomatched_512x256_1view_b64_flash.yaml"
    )
    validation = validate_inputs(repo_root, config_path)
    if "--validate-only" in sys.argv[1:]:
        print(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    output_dir = Path(required_env("AR2_OUTPUT_DIR")).resolve()
    results_dir = Path(required_env("AR2_RESULTS_DIR")).resolve()
    gpu_id = required_env("AR2_GPU_ID")
    events_path = output_dir / "events.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(repo_root / "scripts" / "train.py"),
        "--config_select",
        str(config_path),
        "--set",
        "CUDA_VISIBLE_DEVICES='{}'".format(gpu_id),
        "--set",
        "gpu_id='0'",
    ]
    completed = subprocess.run(command, cwd=str(repo_root), check=False)
    if completed.returncode != 0:
        return completed.returncode

    payload = best_eval_result(events_path, output_dir)
    payload["metrics"].update(
        {
            "selected_gpu": float(gpu_id),
            "planned_epochs": float(TOTAL_EPOCHS),
            "config_batch_size_per_modality": float(CONFIG_BATCH_SIZE),
            "effective_cross_modal_images": float(CONFIG_BATCH_SIZE * 2),
            "identities_per_batch": float(CONFIG_BATCH_SIZE // NUM_POS),
        }
    )
    atomic_write_json(results_dir / "metrics.json", payload)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("Stage-A batch comparison failed: {}".format(exc), file=sys.stderr)
        sys.exit(1)
