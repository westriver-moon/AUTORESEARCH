from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from autoresearch_v2_common import AutoresearchV2Error, file_lock, read_json, utc_now, write_json


def _lease_file(root: Path, gpu_id: str) -> Path:
    return root / f"{gpu_id}.json"


def _query_gpus() -> list[dict[str, Any]]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AutoresearchV2Error(f"nvidia-smi failed: {completed.stderr.strip() or completed.stdout.strip()}")
    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            rows.append(
                {
                    "id": str(int(float(parts[0]))),
                    "memory_used": int(float(parts[1])),
                    "utilization": 0 if parts[2].upper() == "N/A" else int(float(parts[2])),
                }
            )
        except ValueError:
            continue
    return rows


def acquire_gpu_lease(
    root: Path,
    *,
    selector: str,
    owner: str,
    wait_seconds: int,
    max_memory_used: int = 1024,
    max_utilization: int = 10,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + max(wait_seconds, 0)
    requested = selector.strip().lower()
    while True:
        with file_lock(root / ".lock"):
            gpus = _query_gpus()
            candidates = []
            for gpu in gpus:
                if requested not in {"", "auto"} and gpu["id"] not in requested.split(","):
                    continue
                if gpu["memory_used"] > max_memory_used or gpu["utilization"] > max_utilization:
                    continue
                lease = read_json(_lease_file(root, gpu["id"]), default={}) or {}
                lease_owner = str(lease.get("owner") or "")
                if lease_owner and lease_owner != owner:
                    continue
                candidates.append(gpu)
            candidates.sort(key=lambda item: (item["memory_used"], item["utilization"], int(item["id"])))
            if candidates:
                selected = candidates[0]
                lease = {
                    "gpu": selected["id"],
                    "owner": owner,
                    "acquired_at": utc_now(),
                    "memory_used": selected["memory_used"],
                    "utilization": selected["utilization"],
                }
                write_json(_lease_file(root, selected["id"]), lease)
                return lease
        if time.time() >= deadline:
            raise AutoresearchV2Error("No eligible GPU lease became available before the wait budget expired.")
        time.sleep(5)


def release_gpu_lease(root: Path, gpu_id: str) -> None:
    if not gpu_id:
        return
    path = _lease_file(root, gpu_id)
    if path.exists():
        path.unlink()
