#!/usr/bin/env python3
"""Build the RegDB portion of the AAAI-27 evidence bundle from completed runs.

This script is deliberately evidence-only: it never launches training and never
deletes source artifacts.  It selects the epoch with the highest mAP for each
official trial and keeps the paired Rank-1/mINP values from that same event.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any


SOURCE_COMMIT = "c476f51f92aeec9a62e80454608dc25ba1417991"
EXPECTED_PAPER_ROW = {"rank1": 0.907282, "map": 0.845314, "minp": 0.709206}

RUNS = {
    1: Path("/home/lab929/ybj/experiments/regdb_qwen_text_confirm_t15_20260728/runs/QTXT-T01-IID-P050"),
    3: Path("/home/lab929/ybj/experiments/regdb_qwen_text_screen_t03_20260728/runs/QTXT-T03-IID-P050"),
    5: Path("/home/lab929/ybj/experiments/regdb_qwen_text_confirm_t15_20260728/runs/QTXT-T05-IID-P050"),
}
for _trial in (2, 4, 6, 7, 8, 9, 10):
    RUNS[_trial] = Path(
        f"/home/lab929/ybj/experiments/regdb_qwen_pa070_full10_20260728/"
        f"runs/trial_{_trial:02d}/stage_b"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_for(config: Path) -> str:
    return f"python main.py --config_select {config}"


def read_eval_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            if item.get("event_type") == "eval_epoch" and item.get("metrics"):
                events.append(item)
    if not events:
        raise RuntimeError(f"No evaluation events in {path}")
    return events


def yaml_scalar(text: str, key: str, default: str = "") -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*([^#\n]+)", text)
    return match.group(1).strip().strip("'\"") if match else default


def safe_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.output.resolve()
    records = root / "final_runtime_records"
    detail_root = records / "regdb_configs_commands"
    checkpoints = root / "preserved_checkpoints"
    root.mkdir(parents=True, exist_ok=True)
    detail_root.mkdir(parents=True, exist_ok=True)
    checkpoints.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "official_trial", "seed", "direction", "rank1", "map", "minp",
        "selected_epoch", "source_commit", "runtime_config_sha256",
        "command_sha256", "checkpoint_sha256", "metric_file_sha256", "status",
    ]
    rows: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []

    for trial, run in sorted(RUNS.items()):
        config = run / "runtime_config.yaml"
        events_path = run / "events.jsonl"
        manifest_path = run / "manifest.json"
        status_path = run / "status.json"
        for required in (config, events_path, manifest_path, status_path):
            if not required.exists():
                raise FileNotFoundError(required)

        config_text = config.read_text(encoding="utf-8")
        events = read_eval_events(events_path)
        selected = max(events, key=lambda item: float(item["metrics"]["mAP"]))
        metrics = selected["metrics"]
        checkpoint = Path(selected["checkpoint_paths"]["mAP"])
        if not checkpoint.exists():
            raise FileNotFoundError(checkpoint)

        config_hash = sha256(config)
        event_hash = sha256(events_path)
        checkpoint_hash = sha256(checkpoint)
        command = command_for(config)
        command_hash = hashlib.sha256(command.encode("utf-8")).hexdigest()
        status_payload = json.loads(status_path.read_text(encoding="utf-8"))
        status = "complete" if status_payload.get("status") == "succeeded" else "invalid"

        row = {
            "official_trial": trial,
            "seed": int(yaml_scalar(config_text, "seed", "0")),
            "direction": "thermal-to-visible",
            "rank1": f"{float(metrics['Rank-1']):.10f}",
            "map": f"{float(metrics['mAP']):.10f}",
            "minp": f"{float(metrics['mINP']):.10f}",
            "selected_epoch": int(selected["epoch"]),
            "source_commit": SOURCE_COMMIT,
            "runtime_config_sha256": config_hash,
            "command_sha256": command_hash,
            "checkpoint_sha256": checkpoint_hash,
            "metric_file_sha256": event_hash,
            "status": status,
        }
        rows.append(row)

        trial_dir = detail_root / f"trial_{trial:02d}"
        safe_copy(config, trial_dir / "runtime_config.yaml")
        safe_copy(manifest_path, trial_dir / "manifest.json")
        safe_copy(status_path, trial_dir / "status.json")
        (trial_dir / "command.txt").write_text(command + "\n", encoding="utf-8")
        (trial_dir / "selected_metric_event.json").write_text(
            json.dumps(selected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (trial_dir / "checkpoint_record.json").write_text(
            json.dumps(
                {
                    "filename": checkpoint.name,
                    "size_bytes": checkpoint.stat().st_size,
                    "sha256": checkpoint_hash,
                    "source_location_redacted": f"trial_{trial:02d}/{checkpoint.name}",
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        inventory.append(
            {
                "checkpoint_id": f"regdb_trial_{trial:02d}_selected_map",
                "dataset": "RegDB",
                "official_trial": trial,
                "selected_epoch": int(selected["epoch"]),
                "filename": checkpoint.name,
                "size_bytes": checkpoint.stat().st_size,
                "sha256": checkpoint_hash,
                "exists": True,
                "preservation": "source retained; representative trial 04 hard-linked into export"
                if trial == 4
                else "source retained and checksum recorded",
            }
        )

        if trial == 4:
            representative = checkpoints / "regdb_trial04_selected_mAP_epoch21.pth"
            if representative.exists() or representative.is_symlink():
                representative.unlink()
            try:
                os.link(checkpoint, representative)
            except OSError:
                shutil.copy2(checkpoint, representative)

    csv_path = records / "regdb_final_10trials.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    mean = {
        "rank1": sum(float(row["rank1"]) for row in rows) / len(rows),
        "map": sum(float(row["map"]) for row in rows) / len(rows),
        "minp": sum(float(row["minp"]) for row in rows) / len(rows),
    }
    tolerance = 5e-7
    matches = all(abs(mean[key] - EXPECTED_PAPER_ROW[key]) <= tolerance for key in mean)
    audit = {
        "row_count": len(rows),
        "selection_rule": "highest mAP; paired Rank-1 and mINP from the same epoch",
        "computed_mean_fraction": mean,
        "computed_mean_percent": {key: value * 100 for key, value in mean.items()},
        "requested_reference_fraction": EXPECTED_PAPER_ROW,
        "requested_reference_percent": {key: value * 100 for key, value in EXPECTED_PAPER_ROW.items()},
        "matches_requested_reference": matches,
        "packaging_status": "PASS" if matches else "STOP_SOURCE_MISMATCH",
        "note": "The requested reference equals the recorded Trial 4 selected-mAP row, not the recomputed ten-trial mean."
        if not matches
        else "Ten-trial mean matches the requested reference.",
    }
    (records / "regdb_10trial_recompute_output.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    recompute_script = records / "recompute_tables.py"
    recompute_script.write_text(
        "#!/usr/bin/env python3\n"
        "import csv, json, pathlib\n"
        "p=pathlib.Path(__file__).with_name('regdb_final_10trials.csv')\n"
        "rows=list(csv.DictReader(p.open(encoding='utf-8')))\n"
        "mean={k:sum(float(r[k]) for r in rows)/len(rows) for k in ('rank1','map','minp')}\n"
        "print(json.dumps({'rows':len(rows),'mean_fraction':mean,'mean_percent':{k:v*100 for k,v in mean.items()}},indent=2))\n",
        encoding="utf-8",
    )

    inv_fields = list(inventory[0].keys())
    with (root / "checkpoint_inventory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=inv_fields)
        writer.writeheader()
        writer.writerows(inventory)

    (checkpoints / "PRESERVED_CHECKPOINTS.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
