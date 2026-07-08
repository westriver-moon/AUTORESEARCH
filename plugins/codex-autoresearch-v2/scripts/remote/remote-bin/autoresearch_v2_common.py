from __future__ import annotations

import contextlib
import fnmatch
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

import yaml


RUN_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
RESULTS_HEADER = [
    "timestamp",
    "worker",
    "phase",
    "branch",
    "commit",
    "metric",
    "best_metric_before",
    "delta",
    "decision",
    "budget_minutes",
    "run_dir",
    "notes",
]


class AutoresearchV2Error(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_run_tag(value: str) -> str:
    if not RUN_TAG_RE.match(value or ""):
        raise AutoresearchV2Error(f"Invalid run tag: {value!r}")
    return value


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, data: Any) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def append_results_row(path: Path, row: dict[str, Any]) -> None:
    ensure_parent(path)
    if not path.exists():
        path.write_text("\t".join(RESULTS_HEADER) + "\n", encoding="utf-8")
    values = []
    for key in RESULTS_HEADER:
        value = row.get(key, "")
        if value is None:
            value = ""
        text = str(value).replace("\t", " ").replace("\n", " ")
        values.append(text)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\t".join(values) + "\n")


def parse_markdown_front_matter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AutoresearchV2Error(f"{path} must start with YAML front matter.")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise AutoresearchV2Error(f"{path} is missing a closing YAML front matter fence.")
    payload = yaml.safe_load(text[4:end]) or {}
    if not isinstance(payload, dict):
        raise AutoresearchV2Error(f"{path} front matter must decode to a mapping.")
    return payload


def ensure_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AutoresearchV2Error(f"{label} must be a mapping.")
    return value


def ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AutoresearchV2Error(f"{label} must be a non-empty string.")
    return value.strip()


def ensure_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise AutoresearchV2Error(f"{label} must be a non-empty list.")
    return value


def load_program_spec(path: Path) -> dict[str, Any]:
    raw = parse_markdown_front_matter(path)
    direction = ensure_string(raw.get("direction"), "program.direction")
    if direction not in {"higher", "lower"}:
        raise AutoresearchV2Error("program.direction must be 'higher' or 'lower'.")
    worker_count = raw.get("worker_count")
    if not isinstance(worker_count, int) or worker_count < 1:
        raise AutoresearchV2Error("program.worker_count must be a positive integer.")
    return {
        "goal": ensure_string(raw.get("goal"), "program.goal"),
        "metric": ensure_string(raw.get("metric"), "program.metric"),
        "direction": direction,
        "budget_mode": ensure_string(raw.get("budget_mode"), "program.budget_mode"),
        "worker_count": worker_count,
        "keep_threshold": float(raw.get("keep_threshold", 0.0)),
        "stop_conditions": [str(item) for item in raw.get("stop_conditions", [])],
        "mutable_paths": [str(item) for item in raw.get("mutable_paths", [])],
        "notes": [str(item) for item in raw.get("notes", [])],
    }


def load_target_spec(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise AutoresearchV2Error("target YAML must decode to a mapping.")
    repo = ensure_mapping(raw.get("repo"), "target.repo")
    run = ensure_mapping(raw.get("run"), "target.run")
    metric = ensure_mapping(run.get("metric"), "target.run.metric")
    gpu = ensure_mapping(raw.get("gpu") or {}, "target.gpu")
    training = ensure_mapping(raw.get("training") or {}, "target.training")
    return {
        "name": ensure_string(raw.get("name"), "target.name"),
        "repo": {
            "remote_root": ensure_string(repo.get("remote_root"), "target.repo.remote_root"),
            "base_ref": ensure_string(repo.get("base_ref"), "target.repo.base_ref"),
            "mutable_paths": [str(item) for item in ensure_list(repo.get("mutable_paths"), "target.repo.mutable_paths")],
            "readonly_paths": [str(item) for item in repo.get("readonly_paths", [])],
        },
        "run": {
            "cwd": str(run.get("cwd") or "."),
            "command": [ensure_string(item, "target.run.command") for item in ensure_list(run.get("command"), "target.run.command")],
            "budget_minutes": {str(key): int(value) for key, value in dict(run.get("budget_minutes") or {}).items()},
            "metric": {
                "parser": ensure_string(metric.get("parser"), "target.run.metric.parser"),
                "direction": ensure_string(metric.get("direction"), "target.run.metric.direction"),
                "path": str(metric.get("path") or "metrics.json"),
                "primary_key": str(metric.get("primary_key") or "primary_metric"),
            },
            "environment": {str(key): str(value) for key, value in dict(run.get("environment") or {}).items()},
        },
        "artifacts": {
            "collect": [str(item) for item in (raw.get("artifacts") or {}).get("collect", [])],
        },
        "training": {str(key): str(value) for key, value in training.items()},
        "gpu": {
            "policy": str(gpu.get("policy") or "none"),
            "selector": str(gpu.get("selector") or "0"),
            "max_wait_seconds": int(gpu.get("max_wait_seconds") or 0),
        },
    }


def path_in_scope(path: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    normalized = path.replace("\\", "/").lstrip("./")
    candidate = PurePosixPath(normalized)
    for raw_pattern in patterns:
        pattern = raw_pattern.replace("\\", "/").lstrip("./")
        if not pattern:
            continue
        recursive_base = pattern[:-3].rstrip("/") if pattern.endswith("/**") else ""
        if recursive_base and (normalized == recursive_base or normalized.startswith(f"{recursive_base}/")):
            return True
        if pattern.endswith("/") and normalized.startswith(pattern.rstrip("/") + "/"):
            return True
        if not any(marker in pattern for marker in "*?["):
            if normalized == pattern or normalized.startswith(pattern.rstrip("/") + "/"):
                return True
        variants = {pattern}
        while True:
            expanded = {item.replace("**/", "") for item in variants if "**/" in item}
            expanded -= variants
            if not expanded:
                break
            variants |= expanded
        if any(candidate.match(item) for item in variants):
            return True
    return False


def iter_relative_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path.relative_to(root)


def copy_overlay_into_tree(source: Path, destination: Path, allowed_patterns: list[str]) -> list[str]:
    changed: list[str] = []
    if source.is_file():
        rel_paths = [Path(source.name)]
        source_root = source.parent
    else:
        rel_paths = list(iter_relative_files(source))
        source_root = source
    for rel_path in rel_paths:
        rel_text = rel_path.as_posix()
        if not path_in_scope(rel_text, allowed_patterns):
            continue
        src = source_root / rel_path
        dst = destination / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        previous = dst.read_bytes() if dst.exists() else None
        current = src.read_bytes()
        if previous != current:
            shutil.copy2(src, dst)
            changed.append(rel_text)
    return changed


def export_tree_subset(source_root: Path, destination_root: Path, allowed_patterns: list[str]) -> list[str]:
    copied: list[str] = []
    for rel_path in iter_relative_files(source_root):
        rel_text = rel_path.as_posix()
        if not path_in_scope(rel_text, allowed_patterns):
            continue
        src = source_root / rel_path
        dst = destination_root / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel_text)
    return copied


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise AutoresearchV2Error(
            f"git {' '.join(args)} failed in {repo}: {completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed


def git_head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def ensure_worktree(repo_root: Path, base_ref: str, branch: str, worktree_root: Path) -> str:
    worktree_root.parent.mkdir(parents=True, exist_ok=True)
    if worktree_root.exists():
        return git_head(worktree_root)
    git(repo_root, "fetch", "--all", "--prune", check=False)
    git(repo_root, "worktree", "add", "-B", branch, str(worktree_root), base_ref)
    return git_head(worktree_root)


def reset_worktree(worktree_root: Path, commit: str) -> None:
    git(worktree_root, "reset", "--hard", commit)
    git(worktree_root, "clean", "-fd", check=False)


def current_branch(worktree_root: Path) -> str:
    return git(worktree_root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def replace_tokens(template: str, mapping: dict[str, Any]) -> str:
    text = template
    for key, value in mapping.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def render_command(tokens: list[str], mapping: dict[str, Any]) -> list[str]:
    return [replace_tokens(token, mapping) for token in tokens]


def worker_name(index: int) -> str:
    return f"w{index}"


def is_pid_running(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        text = (completed.stdout or "") + (completed.stderr or "")
        return str(pid) in text and "No tasks are running" not in text
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def terminate_pid(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    return True


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    ensure_parent(path)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
