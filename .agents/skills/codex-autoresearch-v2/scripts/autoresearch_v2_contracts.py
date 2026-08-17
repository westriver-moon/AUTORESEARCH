from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

import yaml


class ContractError(ValueError):
    pass


def load_program_front_matter(path: str | Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ContractError("program.md must start with YAML front matter.")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ContractError("program.md is missing a closing YAML front matter fence.")
    payload = yaml.safe_load(text[4:end]) or {}
    if not isinstance(payload, dict):
        raise ContractError("program.md front matter must decode to a YAML mapping.")
    return payload


def load_target_config(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ContractError("target YAML must decode to a mapping.")
    return payload


def ensure_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a mapping.")
    return value


def ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string.")
    return value.strip()


def ensure_list_of_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{label} must be a non-empty list.")
    normalized: list[str] = []
    for item in value:
        normalized.append(ensure_string(item, label))
    return normalized


def ensure_optional_list_of_strings(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ContractError(f"{label} must be a list.")
    return [ensure_string(item, label) for item in value]


def ensure_relative_path(value: Any, label: str) -> str:
    text = ensure_string(value, label).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise ContractError(f"{label} must be a contained relative path.")
    return text


def ensure_finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{label} must be a JSON number.")
    result = float(value)
    if not math.isfinite(result):
        raise ContractError(f"{label} must be finite.")
    return result


def validate_program_dict(data: dict[str, Any]) -> dict[str, Any]:
    goal = ensure_string(data.get("goal"), "goal")
    metric = ensure_string(data.get("metric"), "metric")
    direction = ensure_string(data.get("direction"), "direction")
    if direction not in {"higher", "lower"}:
        raise ContractError("direction must be 'higher' or 'lower'.")
    budget_mode = ensure_string(data.get("budget_mode"), "budget_mode")
    worker_count = data.get("worker_count")
    if not isinstance(worker_count, int) or worker_count < 1:
        raise ContractError("worker_count must be a positive integer.")
    keep_threshold = float(data.get("keep_threshold", 0.0))
    mutable_paths = data.get("mutable_paths") or []
    if mutable_paths and not isinstance(mutable_paths, list):
        raise ContractError("mutable_paths must be a list when provided.")
    return {
        "goal": goal,
        "metric": metric,
        "direction": direction,
        "budget_mode": budget_mode,
        "worker_count": worker_count,
        "keep_threshold": keep_threshold,
        "stop_conditions": list(data.get("stop_conditions") or []),
        "mutable_paths": [str(item) for item in mutable_paths],
        "notes": list(data.get("notes") or []),
    }


def validate_target_dict(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema_version") != 2:
        raise ContractError("unsupported-schema: target schema_version must be integer 2.")
    name = ensure_string(data.get("name"), "name")
    repo = ensure_mapping(data.get("repo"), "repo")
    run = ensure_mapping(data.get("run"), "run")
    metric = ensure_mapping(data.get("metric"), "metric")
    gpu = ensure_mapping(data.get("gpu") or {"mode": "none"}, "gpu")
    provenance = ensure_mapping(data.get("provenance") or {}, "provenance")
    repo_path = ensure_string(repo.get("path"), "repo.path")
    repo_base_ref = ensure_string(repo.get("base_ref") or "HEAD", "repo.base_ref")
    mutable_paths = ensure_list_of_strings(repo.get("mutable_paths"), "repo.mutable_paths")
    argv = ensure_list_of_strings(run.get("argv"), "run.argv")
    environment = ensure_mapping(run.get("env") or {}, "run.env")
    budget_minutes = run.get("budget_minutes", 30)
    if isinstance(budget_minutes, bool) or not isinstance(budget_minutes, int) or budget_minutes < 1:
        raise ContractError("run.budget_minutes must be a positive integer.")
    direction = ensure_string(metric.get("direction"), "metric.direction")
    if direction not in {"higher", "lower"}:
        raise ContractError("metric.direction must be 'higher' or 'lower'.")
    metric_path = ensure_relative_path(metric.get("path") or "metrics.json", "metric.path")
    primary_key = ensure_string(metric.get("primary_key") or "primary_metric", "metric.primary_key")
    if primary_key != "primary_metric":
        raise ContractError("metric.primary_key must be 'primary_metric' in schema_version 2.")
    gpu_mode = ensure_string(gpu.get("mode") or "none", "gpu.mode")
    if gpu_mode not in {"none", "lease"}:
        raise ContractError("gpu.mode must be 'none' or 'lease'.")
    return {
        "schema_version": 2,
        "name": name,
        "repo": {
            "path": repo_path,
            "base_ref": repo_base_ref,
            "mutable_paths": mutable_paths,
            "readonly_paths": ensure_optional_list_of_strings(repo.get("readonly_paths"), "repo.readonly_paths"),
        },
        "run": {
            "cwd": ensure_relative_path(run.get("cwd") or ".", "run.cwd"),
            "argv": argv,
            "env": {ensure_string(key, "run.env key"): ensure_string(value, f"run.env.{key}") for key, value in environment.items()},
            "budget_minutes": budget_minutes,
        },
        "metric": {
            "path": metric_path,
            "primary_key": primary_key,
            "direction": direction,
        },
        "artifacts": [
            ensure_relative_path(item, "artifacts")
            for item in ensure_optional_list_of_strings(data.get("artifacts"), "artifacts")
        ],
        "provenance": {
            "inputs": [
                ensure_relative_path(item, "provenance.inputs")
                for item in ensure_optional_list_of_strings(provenance.get("inputs"), "provenance.inputs")
            ],
        },
        "gpu": {
            "mode": gpu_mode,
            "selector": str(gpu.get("selector") or "0"),
            "max_wait_seconds": int(gpu.get("max_wait_seconds") or 0),
        },
    }


def as_json_summary(program: dict[str, Any] | None = None, target: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {"ok": True}
    if program is not None:
        payload["program"] = program
    if target is not None:
        payload["target"] = target
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate autoresearch v2 contracts")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate-program").add_argument("--path", required=True)
    commands.add_parser("validate-target").add_argument("--path", required=True)
    args = parser.parse_args()

    if args.command == "validate-program":
        print(as_json_summary(program=validate_program_dict(load_program_front_matter(args.path))))
    else:
        print(as_json_summary(target=validate_target_dict(load_target_config(args.path))))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc
