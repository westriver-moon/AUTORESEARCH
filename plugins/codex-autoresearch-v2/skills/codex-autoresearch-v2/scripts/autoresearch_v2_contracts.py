from __future__ import annotations

import json
from pathlib import Path
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
    name = ensure_string(data.get("name"), "name")
    repo = ensure_mapping(data.get("repo"), "repo")
    run = ensure_mapping(data.get("run"), "run")
    metric = ensure_mapping(run.get("metric"), "run.metric")
    repo_remote_root = ensure_string(repo.get("remote_root"), "repo.remote_root")
    repo_base_ref = ensure_string(repo.get("base_ref"), "repo.base_ref")
    mutable_paths = ensure_list_of_strings(repo.get("mutable_paths"), "repo.mutable_paths")
    command = run.get("command")
    if not isinstance(command, list) or not command:
        raise ContractError("run.command must be a non-empty list.")
    command = [ensure_string(item, "run.command") for item in command]
    parser_name = ensure_string(metric.get("parser"), "run.metric.parser")
    direction = ensure_string(metric.get("direction"), "run.metric.direction")
    if direction not in {"higher", "lower"}:
        raise ContractError("run.metric.direction must be 'higher' or 'lower'.")
    return {
        "name": name,
        "repo": {
            "remote_root": repo_remote_root,
            "base_ref": repo_base_ref,
            "mutable_paths": mutable_paths,
            "readonly_paths": [str(item) for item in repo.get("readonly_paths") or []],
        },
        "run": {
            "cwd": str(run.get("cwd") or "."),
            "command": command,
            "budget_minutes": dict(run.get("budget_minutes") or {}),
            "metric": {
                "parser": parser_name,
                "direction": direction,
                "path": str(metric.get("path") or "metrics.json"),
                "primary_key": str(metric.get("primary_key") or "primary_metric"),
            },
        },
        "artifacts": {
            "collect": [str(item) for item in (data.get("artifacts") or {}).get("collect", [])],
        },
        "training": dict(data.get("training") or {}),
        "gpu": dict(data.get("gpu") or {}),
    }


def as_json_summary(program: dict[str, Any] | None = None, target: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {"ok": True}
    if program is not None:
        payload["program"] = program
    if target is not None:
        payload["target"] = target
    return json.dumps(payload, ensure_ascii=False, indent=2)
