from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml


def prepare_tvilfm_config(
    *,
    source_config: Path,
    destination_config: Path,
    run_output_dir: Path,
    data_root: str,
    pretrained: str,
    gpu: str,
) -> None:
    payload = yaml.safe_load(source_config.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"training config must be a YAML mapping: {source_config}")
    payload["output_path"] = run_output_dir.as_posix().rstrip("/") + "/"
    payload["sysu_data_path"] = data_root.rstrip("/") + "/"
    payload["pmt_pretrained"] = pretrained
    payload["CUDA_VISIBLE_DEVICES"] = gpu
    payload["gpu_id"] = "0"
    destination_config.parent.mkdir(parents=True, exist_ok=True)
    destination_config.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def parse_tvilfm_metric(run_output_dir: Path, results_dir: Path) -> dict[str, Any]:
    results_dir.mkdir(parents=True, exist_ok=True)
    metric_path = results_dir / "metrics.json"
    metrics_jsonl = run_output_dir / "metrics.jsonl"
    if metrics_jsonl.exists():
        last = ""
        for line in metrics_jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = line.strip()
        if last:
            payload = json.loads(last)
            metric_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return payload

    number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    best_re = re.compile(
        rf"Best .*?mINP:\s*({number}).*?Best mAP:\s*({number}).*?Best Rank1:\s*({number})",
        re.IGNORECASE,
    )
    minp_re = re.compile(rf"^\s*mINP:\s*({number})", re.IGNORECASE)
    map_re = re.compile(rf"^\s*mAP:\s*({number})", re.IGNORECASE)
    rank_re = re.compile(rf"^\s*Rank:\s*\[?\s*({number})", re.IGNORECASE)

    best_rank1 = best_map = best_minp = None
    evals: list[dict[str, Any]] = []
    log_candidates = sorted(run_output_dir.glob("**/logs/log.log"), key=lambda item: item.stat().st_mtime, reverse=True)
    for log_path in log_candidates:
        pending = {"mINP": None, "mAP": None, "rank1": None, "lines": []}
        for line_no, raw_line in enumerate(log_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            best_match = best_re.search(raw_line)
            if best_match:
                best_minp, best_map, best_rank1 = map(float, best_match.groups())
            minp_match = minp_re.search(raw_line)
            map_match = map_re.search(raw_line)
            rank_match = rank_re.search(raw_line)
            if minp_match:
                pending = {"mINP": float(minp_match.group(1)), "mAP": None, "rank1": None, "lines": [(line_no, raw_line)]}
            elif map_match:
                pending["mAP"] = float(map_match.group(1))
                pending["lines"].append((line_no, raw_line))
            elif rank_match:
                pending["rank1"] = float(rank_match.group(1))
                pending["lines"].append((line_no, raw_line))
                evals.append(
                    {
                        "mINP": pending["mINP"],
                        "mAP": pending["mAP"],
                        "rank1": pending["rank1"],
                        "raw_block": "\n".join(item for _, item in pending["lines"]),
                    }
                )
                pending = {"mINP": None, "mAP": None, "rank1": None, "lines": []}
        if evals:
            break

    if not evals:
        payload = {"available": False, "reason": "no TVI-LFM metric line found"}
        metric_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    last = evals[-1]
    primary_metric = best_map if best_map is not None else last["mAP"]
    payload = {
        "available": True,
        "schema_version": "reid-metrics-v1",
        "source_format": "tvilfm_log",
        "metric_name": "mAP",
        "direction": "higher",
        "primary_metric": primary_metric,
        "primary_metric_source": "best_mAP" if best_map is not None else "last_mAP",
        "mAP": last["mAP"],
        "rank1": last["rank1"],
        "mINP": last["mINP"],
        "best_mAP": best_map,
        "best_rank1": best_rank1,
        "best_mINP": best_minp,
        "raw_block": last["raw_block"],
    }
    metric_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
