#!/usr/bin/env python3
"""Assemble non-multiseed AAAI-27 evidence on the 3090 server.

Large immutable inputs are hard-linked on the same filesystem to preserve them
without duplicating disk blocks. Existing files are never deleted or modified.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path("/home/cgv841/ybj/AAAI27_SERVER_EXPORT_20260731")
VISUAL_SOURCE = Path("/home/cgv841/ybj/SALT_VI_PAPER_VISUALS_20260728")
IR_AUDIT_SOURCE = Path(
    "/home/cgv841/ybj/TVI-LFM/model_visualization/irtext_reliability_20260728"
)
SYSU_TEXT = Path("/home/cgv841/ybj/TVI-LFM/datasets/sysu/Text")
REGDB_TEXT = Path("/home/cgv841/ybj/TVI-LFM/datasets/regdb/Text")
SYSU_QWEN = Path("/home/cgv841/datasets/SYSU-MM01/Text/Blip_RGB_Qwen3_14B_AWQ")
REGDB_QWEN = Path("/home/cgv841/datasets/RegDB/Text/Blip_RGB_Qwen3_14B_AWQ")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload) -> None:
    atomic_text(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def preserve_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or destination.stat().st_size != source.stat().st_size:
            raise FileExistsError(f"Conflicting preserved path: {destination}")
        return
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def preserve_tree(source: Path, destination: Path, *, predicate=None) -> None:
    if not source.is_dir():
        raise FileNotFoundError(source)
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if predicate is not None and not predicate(relative):
            continue
        preserve_file(path, destination / relative)


def json_structure(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = {"type": type(payload).__name__}
    if isinstance(payload, dict):
        result["records"] = len(payload)
        values = list(payload.values())
        if values:
            result["value_types"] = sorted({type(value).__name__ for value in values})
            list_lengths = [len(value) for value in values if isinstance(value, list)]
            if list_lengths:
                result["list_length_min"] = min(list_lengths)
                result["list_length_max"] = max(list_lengths)
            if all(isinstance(value, dict) and "paraphrases" in value for value in values):
                counts = [len(value.get("paraphrases", [])) for value in values]
                result["paraphrases_min"] = min(counts)
                result["paraphrases_max"] = max(counts)
                result["all_have_four_paraphrases"] = all(count == 4 for count in counts)
                result["all_have_source_description"] = all(
                    isinstance(value.get("description"), str) and bool(value["description"].strip())
                    for value in values
                )
    elif isinstance(payload, list):
        result["records"] = len(payload)
    return result


def npy_structure(path: Path) -> dict:
    array = np.load(path, allow_pickle=True, mmap_mode=None)
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "records": int(array.shape[0]) if array.ndim else 1,
    }


def sanitized_generation_metadata(source: Path) -> dict:
    manifest = json.loads((source / "manifest.shard-000-of-001.json").read_text(encoding="utf-8"))
    journal = source / "paraphrases.shard-000-of-001.jsonl"
    seeds = []
    valid_lines = 0
    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        valid_lines += 1
        if "seed" in row:
            seeds.append(int(row["seed"]))
    return {
        "schema_version": manifest.get("schema_version"),
        "model": manifest.get("model"),
        "revision": manifest.get("revision"),
        "prompt_version": manifest.get("prompt_version"),
        "generation": manifest.get("generation"),
        "expected_total": manifest.get("expected_total"),
        "completed": manifest.get("completed"),
        "coverage": manifest.get("coverage"),
        "complete": manifest.get("complete"),
        "source_filename": Path(str(manifest.get("source", "unknown"))).name,
        "source_sha256": manifest.get("source_sha256"),
        "journal_valid_lines": valid_lines,
        "journal_seed_count": len(seeds),
        "journal_seed_min": min(seeds) if seeds else "not recorded",
        "journal_seed_max": max(seeds) if seeds else "not recorded",
        "note": "Absolute model/data paths were intentionally removed for anonymous export.",
    }


def assemble_caption_resources() -> None:
    destination = ROOT / "caption_manifests"
    files = {
        "sysu/source_rgb": SYSU_TEXT / "Blip_RGB",
        "sysu/inherited_ir": SYSU_TEXT / "Blip_IR",
        "regdb/source_rgb": REGDB_TEXT / "Blip_RGB",
        "regdb/inherited_ir": REGDB_TEXT / "Blip_IR",
    }
    for relative, source in files.items():
        preserve_tree(source, destination / "resources" / relative)
    preserve_file(
        SYSU_QWEN / "caption_qwen3_14b_awq_4x.json",
        destination / "resources/sysu/qwen/caption_qwen3_14b_awq_4x.json",
    )
    preserve_file(
        REGDB_QWEN / "caption_qwen3_14b_awq_4x.json",
        destination / "resources/regdb/qwen/caption_qwen3_14b_awq_4x.json",
    )
    metadata = {
        "generated_at": now(),
        "sysu": sanitized_generation_metadata(SYSU_QWEN),
        "regdb": sanitized_generation_metadata(REGDB_QWEN),
    }
    atomic_json(destination / "generation_metadata.json", metadata)

    rows = []
    validation = {"generated_at": now(), "files": {}, "errors": []}
    resource_root = destination / "resources"
    for path in sorted(resource_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(destination).as_posix()
        record = {
            "relative_path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
            "kind": path.suffix.lower().lstrip("."),
            "status": "valid",
        }
        try:
            if path.suffix.lower() == ".json":
                details = json_structure(path)
            elif path.suffix.lower() == ".npy":
                details = npy_structure(path)
            else:
                details = {"note": "hash-only validation"}
        except Exception as error:  # Preserve evidence and report, never hide failures.
            details = {"error": f"{type(error).__name__}: {error}"}
            record["status"] = "invalid"
            validation["errors"].append({"relative_path": relative, **details})
        validation["files"][relative] = details
        rows.append(record)
    with (destination / "caption_file_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    validation["status"] = "valid" if not validation["errors"] else "errors_present"
    validation["file_count"] = len(rows)
    atomic_json(destination / "structural_validation.json", validation)


def assemble_existing_visuals() -> None:
    preserve_tree(VISUAL_SOURCE, ROOT / "visual_evidence/existing_sysu_package")
    preserve_tree(IR_AUDIT_SOURCE, ROOT / "visual_evidence/caption_panels/inherited_ir_audit")
    token_source = Path(
        "/home/cgv841/ybj/TVI-LFM/reports/token_aware_pa05_attention_analysis"
    )
    if token_source.is_dir():
        preserve_tree(token_source, ROOT / "visual_evidence/representation_diagnostics/legacy_token_attention")


def assemble_training_records() -> None:
    stage1 = Path("/home/cgv841/ybj/TVI-LFM/train_outputs/stage_a_pmt_recipe_mbpatch_30")
    stage2 = Path("/home/cgv841/ybj/TVI-LFM/reports/a3_e4_hpt_stage3/runs/A3E4-S3-PAIR-EQUAL")
    qwen = Path("/home/cgv841/ybj/experiments/qwen_text_aug_grid_e30_20260727/T3_balanced50")
    stage1_names = {
        "COMMANDS.md", "COMPARABILITY_REPORT.md", "LOG.md", "RESULT_ANALYSIS.md",
        "SCIENTIFIC_CHANGELOG.md", "SUMMARY.md", "mbpatch_eval_metrics.csv",
        "mbpatch_result_summary.json", "mbpatch_summary_metrics.csv",
        "mbpatch_train_metrics.csv", "status.json",
    }
    preserve_tree(
        stage1,
        ROOT / "visual_evidence/training_curves/stage1",
        predicate=lambda relative: relative.name in stage1_names or relative.parts[0] == "plots",
    )
    for name in (
        "runtime_config.yaml", "command.txt", "events.jsonl", "status.json",
        "source_state.json", "environment.json", "artifact_hashes.json",
    ):
        path = stage2 / name
        if path.is_file():
            preserve_file(path, ROOT / "visual_evidence/training_curves/stage2_8365" / name)
    for name in ("events.jsonl", "summary.json", "train.log", "exit_code"):
        path = qwen / name
        if path.is_file():
            preserve_file(path, ROOT / "visual_evidence/training_curves/stage2_qwen_seed0" / name)


def assemble_checkpoints() -> None:
    checkpoints = [
        (
            "sysu_stage1_a3_epoch24.pth",
            Path("/home/cgv841/ybj/TVI-LFM/checkpoints/stage_a/a3_epoch24_tvilfm_full.pth"),
            "SYSU", "Stage-I selected initialization",
        ),
        (
            "sysu_two_stage_baseline_epoch21.pth",
            Path(
                "/home/cgv841/ybj/TVI-LFM/reports/a3_e4_hpt_l025/e4/model_output/sysu/FV/"
                "Baseline_train[RGB_IR_Text]_joint[uni]_Blip_parameter_add_id,wrt_Fix_Visual/"
                "models/model_Fusion_21.pth"
            ),
            "SYSU", "Two-stage baseline",
        ),
        (
            "sysu_final_8365_epoch14.pth",
            Path(
                "/home/cgv841/ybj/TVI-LFM/reports/a3_e4_hpt_stage3/runs/A3E4-S3-PAIR-EQUAL/"
                "model_output/sysu/FV/Baseline_train[RGB_IR_Text]_joint[uni]_Blip_parameter_add_"
                "id,cross_modal_hard_Fix_Visual/models/model_Fusion_epoch_14.pth"
            ),
            "SYSU", "83.65 final non-Qwen model",
        ),
        (
            "sysu_qwen_seed0_selected_minp_epoch27.pth",
            Path(
                "/home/cgv841/ybj/experiments/qwen_text_aug_grid_e30_20260727/T3_balanced50/"
                "model_output/sysu/FV/Baseline_train[RGB_IR_Text]_joint[uni]_Blip_parameter_add_"
                "LLM_0.5_id,cross_modal_hard_Fix_Visual/models/model_Fusion_epoch_27.pth"
            ),
            "SYSU", "Qwen/BCC seed-0 highest-mINP checkpoint",
        ),
    ]
    records = []
    for filename, source, dataset, role in checkpoints:
        record = {
            "checkpoint_id": filename[:-4] if filename.endswith(".pth") else filename,
            "dataset": dataset,
            "role": role,
            "filename": filename,
            "exists": source.is_file(),
            "size_bytes": source.stat().st_size if source.is_file() else None,
            "sha256": sha256(source) if source.is_file() else None,
            "preservation": "hard-link in export when same filesystem",
        }
        if source.is_file():
            preserve_file(source, ROOT / "preserved_checkpoints" / filename)
        records.append(record)
    with (ROOT / "checkpoint_inventory_3090.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def environment_snapshot() -> None:
    destination = ROOT / "environment_snapshots/3090_server"
    destination.mkdir(parents=True, exist_ok=True)
    python = "/home/cgv841/anaconda3/envs/clipreid/bin/python"
    probe = subprocess.check_output(
        [
            python,
            "-c",
            "import json,platform,torch,torchvision; print(json.dumps({"
            "'python':platform.python_version(),'torch':torch.__version__,"
            "'torchvision':torchvision.__version__,'torch_cuda':torch.version.cuda,"
            "'cudnn':torch.backends.cudnn.version()}))",
        ],
        text=True,
    )
    versions = json.loads(probe.strip().splitlines()[-1])
    gpu_output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    gpus = []
    for line in gpu_output.splitlines():
        index, name, memory, driver = [item.strip() for item in line.split(",")]
        gpus.append(
            {"index": int(index), "name": name, "memory_total_mib": int(memory), "driver": driver}
        )
    snapshot = {
        "generated_at": now(),
        "source_commits": {
            "sysu_8365": "933c055e2bb1b1e2495065bd8b0c64174bc63f53",
            "sysu_qwen_seed0": "f947081e9b0dd23bdf432b351e7c3e2bee038d53",
        },
        "software": versions,
        "gpus": gpus,
        "host_user_ip_removed": True,
    }
    atomic_json(destination / "environment.json", snapshot)
    freeze = subprocess.check_output([python, "-m", "pip", "freeze"], text=True, errors="replace")
    freeze = re.sub(r"file:///[^\s]+", "file://<LOCAL_BUILD>", freeze)
    freeze = re.sub(r"^-e\s+/[^\n]+$", "-e <LOCAL_EDITABLE_REMOVED>", freeze, flags=re.MULTILINE)
    atomic_text(destination / "pip_freeze_sanitized.txt", freeze)
    runtime_rows = [
        {
            "stage": "SYSU Stage-II 83.65 continuation",
            "start_utc": "2026-07-22T16:45:10+00:00",
            "end_utc": "2026-07-22T21:48:18+00:00",
            "wall_clock_seconds": 18188,
            "peak_gpu_memory": "not recorded",
            "evaluation_batch_size": 8,
        },
        {
            "stage": "SYSU Qwen/BCC seed-0 continuation",
            "start_utc": "2026-07-27T17:11:02.109528+00:00",
            "end_utc": "2026-07-28T00:53:44.847731+00:00",
            "wall_clock_seconds": 27763,
            "peak_gpu_memory": "not recorded",
            "evaluation_batch_size": 8,
        },
    ]
    with (destination / "runtime_resources.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(runtime_rows[0]))
        writer.writeheader()
        writer.writerows(runtime_rows)


def write_export_inventory() -> None:
    rows = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and path.name not in {"EXPORT_SHA256SUMS.txt", "export_inventory.csv"}:
            rows.append(
                {
                    "relative_path": path.relative_to(ROOT).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    with (ROOT / "export_inventory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    atomic_text(
        ROOT / "EXPORT_SHA256SUMS.txt",
        "".join(f"{row['sha256']}  {row['relative_path']}\n" for row in rows),
    )


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    assemble_caption_resources()
    assemble_existing_visuals()
    assemble_training_records()
    assemble_checkpoints()
    environment_snapshot()
    write_export_inventory()
    atomic_json(
        ROOT / "BUILD_STATUS.json",
        {
            "status": "complete",
            "generated_at": now(),
            "multiseed_excluded_by_user": True,
            "deletions_performed": False,
            "note": "RegDB records remain on the 4090 export pending cross-server consolidation.",
        },
    )
    print(json.dumps({"status": "complete", "root": str(ROOT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
