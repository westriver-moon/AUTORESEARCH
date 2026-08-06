#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from autoresearch_v2_common import (
    AutoresearchV2Error,
    append_jsonl,
    append_results_row,
    copy_overlay_into_tree,
    current_branch,
    ensure_run_tag,
    ensure_worktree,
    export_tree_subset,
    file_lock,
    git,
    git_head,
    is_pid_running,
    load_program_spec,
    load_target_spec,
    read_json,
    reset_worktree,
    terminate_pid,
    utc_now,
    worker_name,
    write_json,
)
from autoresearch_v2_gpu_lease import acquire_gpu_lease, release_gpu_lease


SCHEMA_VERSION = "autoresearch-v2-state-schema-2"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remote-first autoresearch v2 controller")
    parser.add_argument("--run-root-base", required=True)
    parser.add_argument("--worktree-root-base", required=True)
    parser.add_argument("--lease-root", required=True)
    parser.add_argument("--run-tag", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_cmd = subparsers.add_parser("doctor")
    doctor_cmd.add_argument("--target")

    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--program", required=True)
    bootstrap.add_argument("--target", required=True)
    bootstrap.add_argument("--branch-prefix", required=True)
    bootstrap.add_argument("--worker-count", type=int, required=True)
    bootstrap.add_argument("--keep-threshold", type=float, default=0.0)
    bootstrap.add_argument("--force", action="store_true")

    inspect_cmd = subparsers.add_parser("inspect")
    inspect_cmd.add_argument("--worker", required=True)

    apply_cmd = subparsers.add_parser("apply")
    apply_cmd.add_argument("--worker", required=True)
    apply_cmd.add_argument("--overlay", required=True)
    apply_cmd.add_argument("--note", default="")

    baseline_cmd = subparsers.add_parser("baseline")
    baseline_cmd.add_argument("--worker", default="w1")
    baseline_cmd.add_argument("--budget-minutes", type=int, default=0)
    baseline_cmd.add_argument("--simulate-metric", type=float)
    baseline_cmd.add_argument("--simulate-delay-seconds", type=float, default=0.0)
    baseline_cmd.add_argument("--foreground", action="store_true")

    run_cmd = subparsers.add_parser("run")
    run_cmd.add_argument("--worker")
    run_cmd.add_argument("--all-workers", action="store_true")
    run_cmd.add_argument("--budget-minutes", type=int, default=0)
    run_cmd.add_argument("--simulate-metric", type=float)
    run_cmd.add_argument("--simulate-delay-seconds", type=float, default=0.0)
    run_cmd.add_argument("--foreground", action="store_true")

    resume_cmd = subparsers.add_parser("resume")
    resume_cmd.add_argument("--worker")
    resume_cmd.add_argument("--all-workers", action="store_true")
    resume_cmd.add_argument("--budget-minutes", type=int, default=0)
    resume_cmd.add_argument("--simulate-metric", type=float)
    resume_cmd.add_argument("--simulate-delay-seconds", type=float, default=0.0)
    resume_cmd.add_argument("--foreground", action="store_true")

    stop_cmd = subparsers.add_parser("stop")
    stop_cmd.add_argument("--worker")
    stop_cmd.add_argument("--all-workers", action="store_true")

    sync_cmd = subparsers.add_parser("sync-best")
    sync_cmd.add_argument("--worker")
    sync_cmd.add_argument("--all-workers", action="store_true")

    subparsers.add_parser("status")
    subparsers.add_parser("collect")

    worker_runner = subparsers.add_parser("worker-runner")
    worker_runner.add_argument("--worker", required=True)
    worker_runner.add_argument("--phase", required=True, choices=["baseline", "run"])
    worker_runner.add_argument("--trial-id", required=True)
    worker_runner.add_argument("--budget-minutes", type=int, required=True)
    worker_runner.add_argument("--simulate-metric", type=float)
    worker_runner.add_argument("--simulate-delay-seconds", type=float, default=0.0)
    return parser


def run_root(args: argparse.Namespace) -> Path:
    return Path(args.run_root_base) / ensure_run_tag(args.run_tag)


def worktree_root(args: argparse.Namespace, worker: str) -> Path:
    return Path(args.worktree_root_base) / ensure_run_tag(args.run_tag) / worker


def state_path(args: argparse.Namespace) -> Path:
    return run_root(args) / "state.json"


def lock_path(args: argparse.Namespace) -> Path:
    return run_root(args) / ".state.lock"


def events_path(args: argparse.Namespace) -> Path:
    return run_root(args) / "events.jsonl"


def results_path(args: argparse.Namespace) -> Path:
    return run_root(args) / "results.tsv"


def leaderboard_path(args: argparse.Namespace) -> Path:
    return run_root(args) / "leaderboard.json"


def worker_status_path(args: argparse.Namespace, worker: str) -> Path:
    return run_root(args) / "workers" / worker / "status.json"


def worker_log_path(args: argparse.Namespace, worker: str) -> Path:
    return run_root(args) / "workers" / worker / "runner.log"


def worker_artifact_root(args: argparse.Namespace, worker: str) -> Path:
    return run_root(args) / "artifacts" / worker


def worker_export_root(args: argparse.Namespace, worker: str) -> Path:
    return run_root(args) / "exports" / worker


def resolve_budget_minutes(state: dict[str, Any], requested: int) -> int:
    if requested > 0:
        return requested
    return int(state["target"]["run"]["budget_minutes"])


def load_state(args: argparse.Namespace) -> dict[str, Any]:
    payload = read_json(state_path(args))
    if not isinstance(payload, dict):
        raise AutoresearchV2Error(f"state file was not found: {state_path(args)}")
    return payload


def save_state(args: argparse.Namespace, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    write_json(state_path(args), state)
    write_json(leaderboard_path(args), build_leaderboard(state))
    for worker, data in state["workers"].items():
        write_json(worker_status_path(args, worker), data)


def build_leaderboard(state: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for worker, data in sorted(state["workers"].items()):
        rows.append(
            {
                "worker": worker,
                "branch": data["branch"],
                "status": data["status"],
                "last_metric": data.get("last_metric"),
                "last_decision": data.get("last_decision"),
                "last_commit": data.get("last_commit"),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "run_tag": state["run_tag"],
        "best_metric": state.get("best_metric"),
        "best_commit": state.get("best_commit"),
        "best_branch": state.get("best_branch"),
        "workers": rows,
    }


def target_mutable_paths(state: dict[str, Any]) -> list[str]:
    program_paths = list(state["program"].get("mutable_paths") or [])
    if program_paths:
        return program_paths
    return list(state["target"]["repo"]["mutable_paths"])


def update_worker_status(
    state: dict[str, Any],
    worker: str,
    *,
    status: str,
    pid: int | None = None,
    last_metric: float | None = None,
    last_decision: str | None = None,
    last_commit: str | None = None,
    last_run_dir: str | None = None,
    trial_id: str | None = None,
    trial_commit: str | None = None,
    run_dir: str | None = None,
    completion_reason: str | None = None,
    process_exit_code: int | None = None,
    metric_extracted: bool | None = None,
    gpu: str | None = None,
    note: str | None = None,
) -> None:
    entry = state["workers"][worker]
    entry["status"] = status
    entry["updated_at"] = utc_now()
    if pid is not None:
        entry["pid"] = pid
    elif status in {"idle", "failed", "stopped", "discarded", "kept"}:
        entry["pid"] = None
    if last_metric is not None:
        entry["last_metric"] = last_metric
    if last_decision is not None:
        entry["last_decision"] = last_decision
    if last_commit is not None:
        entry["last_commit"] = last_commit
    if last_run_dir is not None:
        entry["last_run_dir"] = last_run_dir
    if trial_id is not None:
        entry["trial_id"] = trial_id
    if trial_commit is not None:
        entry["trial_commit"] = trial_commit
    if run_dir is not None:
        entry["run_dir"] = run_dir
    if completion_reason is not None:
        entry["completion_reason"] = completion_reason
    entry["process_exit_code"] = process_exit_code
    if metric_extracted is not None:
        entry["metric_extracted"] = metric_extracted
    if gpu is not None:
        entry["gpu"] = gpu
    if note is not None:
        entry["note"] = note


def ensure_initialized(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise AutoresearchV2Error("state schema version mismatch")
    return state


def git_commit_if_needed(worktree: Path, changed_files: list[str], message: str) -> str:
    if not changed_files:
        return git_head(worktree)
    git(worktree, "add", "--", *changed_files)
    staged = git(worktree, "diff", "--cached", "--name-only").stdout.splitlines()
    if not staged:
        return git_head(worktree)
    git(worktree, "commit", "-m", message)
    return git_head(worktree)


def bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    root = run_root(args)
    if root.exists() and any(root.iterdir()) and not args.force:
        raise AutoresearchV2Error(f"run root already exists: {root}")
    root.mkdir(parents=True, exist_ok=True)

    program_path = Path(args.program)
    target_path = Path(args.target)
    program = load_program_spec(program_path)
    target = load_target_spec(target_path)
    if program["direction"] != target["metric"]["direction"]:
        raise AutoresearchV2Error("program.direction must match target.metric.direction")

    spec_dir = root / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    program_snapshot = spec_dir / "program.md"
    target_snapshot = spec_dir / "target.yaml"
    shutil.copy2(program_path, program_snapshot)
    shutil.copy2(target_path, target_snapshot)

    repo_root = Path(target["repo"]["path"])
    base_ref = target["repo"]["base_ref"]
    if not (repo_root / ".git").exists():
        raise AutoresearchV2Error(f"target repo is not a git repository: {repo_root}")
    best_branch = f"{args.branch_prefix}{args.run_tag}-best"
    base_commit = git(repo_root, "rev-parse", base_ref).stdout.strip()
    git(repo_root, "branch", "-f", best_branch, base_commit)

    workers: dict[str, Any] = {}
    for index in range(1, args.worker_count + 1):
        worker = worker_name(index)
        branch = f"{args.branch_prefix}{args.run_tag}-{worker}"
        tree = worktree_root(args, worker)
        ensure_worktree(repo_root, base_ref, branch, tree)
        workers[worker] = {
            "branch": branch,
            "worktree": str(tree),
            "status": "idle",
            "pid": None,
            "last_metric": None,
            "last_decision": None,
            "last_commit": git_head(tree),
            "last_run_dir": "",
            "trial_id": "",
            "trial_commit": "",
            "run_dir": "",
            "completion_reason": "",
            "process_exit_code": None,
            "metric_extracted": False,
            "gpu": "",
            "note": "",
            "updated_at": utc_now(),
        }

    state = {
        "schema_version": SCHEMA_VERSION,
        "run_tag": args.run_tag,
        "program": program,
        "target": target,
        "program_snapshot": str(program_snapshot),
        "target_snapshot": str(target_snapshot),
        "repo_root": str(repo_root),
        "base_ref": base_ref,
        "best_branch": best_branch,
        "best_commit": base_commit,
        "best_metric": None,
        "keep_threshold": float(args.keep_threshold),
        "baseline": None,
        "next_iteration": 1,
        "workers": workers,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    save_state(args, state)
    return {
        "ok": True,
        "command": "bootstrap",
        "run_root": str(root),
        "best_commit": base_commit,
        "workers": sorted(workers.keys()),
    }


def inspect_worker(args: argparse.Namespace) -> dict[str, Any]:
    state = ensure_initialized(args)
    worker = args.worker
    if worker not in state["workers"]:
        raise AutoresearchV2Error(f"unknown worker: {worker}")
    export_root = worker_export_root(args, worker) / "inspect"
    if export_root.exists():
        shutil.rmtree(export_root)
    copied = export_tree_subset(Path(state["workers"][worker]["worktree"]), export_root, target_mutable_paths(state))
    payload = {
        "ok": True,
        "command": "inspect",
        "worker": worker,
        "export_root": str(export_root),
        "files": copied,
    }
    return payload


def apply_overlay(args: argparse.Namespace) -> dict[str, Any]:
    state = ensure_initialized(args)
    worker = args.worker
    if worker not in state["workers"]:
        raise AutoresearchV2Error(f"unknown worker: {worker}")
    entry = state["workers"][worker]
    if is_pid_running(entry.get("pid")):
        raise AutoresearchV2Error(f"worker is running and cannot accept apply: {worker}")
    overlay = Path(args.overlay)
    if not overlay.exists():
        raise AutoresearchV2Error(f"overlay does not exist: {overlay}")
    changed = copy_overlay_into_tree(overlay, Path(entry["worktree"]), target_mutable_paths(state))
    commit = git_commit_if_needed(
        Path(entry["worktree"]),
        changed,
        message=f"autoresearch {args.run_tag} {worker} apply {args.note or utc_now()}",
    )
    with file_lock(lock_path(args)):
        latest = load_state(args)
        update_worker_status(
            latest,
            worker,
            status="ready" if changed else "idle",
            last_commit=commit,
            note=args.note or ("applied overlay" if changed else "overlay produced no diff"),
        )
        save_state(args, latest)
    return {
        "ok": True,
        "command": "apply",
        "worker": worker,
        "changed_files": changed,
        "commit": commit,
    }


def selected_workers(state: dict[str, Any], worker: str | None, all_workers: bool) -> list[str]:
    if all_workers:
        return sorted(state["workers"].keys())
    if worker:
        if worker not in state["workers"]:
            raise AutoresearchV2Error(f"unknown worker: {worker}")
        return [worker]
    return ["w1"]


def launch_workers(
    args: argparse.Namespace,
    *,
    phase: str,
    worker: str | None,
    all_workers: bool,
    budget_minutes: int,
    simulate_metric: float | None,
    simulate_delay_seconds: float,
    foreground: bool,
) -> dict[str, Any]:
    state = ensure_initialized(args)
    if phase == "baseline":
        with file_lock(lock_path(args)):
            latest = load_state(args)
            baseline_active = any(
                entry.get("status") in {"queued", "running"}
                and str(entry.get("note") or "").startswith("baseline")
                for entry in latest["workers"].values()
            )
            if latest.get("baseline") is not None or baseline_active:
                raise AutoresearchV2Error("baseline already exists or is already running")
    workers = selected_workers(state, worker, all_workers)
    budget = resolve_budget_minutes(state, budget_minutes)
    started: list[dict[str, Any]] = []
    for name in workers:
        with file_lock(lock_path(args)):
            latest = load_state(args)
            entry = latest["workers"][name]
            if is_pid_running(entry.get("pid")):
                started.append({"worker": name, "status": "already_running", "pid": entry.get("pid")})
                continue
            trial_id = f"iter-{latest['next_iteration']:04d}"
            latest["next_iteration"] += 1
            update_worker_status(latest, name, status="queued", trial_id=trial_id, note=f"{phase} queued")
            save_state(args, latest)
        if foreground:
            result = run_worker_once(
                args,
                worker=name,
                phase=phase,
                trial_id=trial_id,
                budget_minutes=budget,
                simulate_metric=simulate_metric,
                simulate_delay_seconds=simulate_delay_seconds,
            )
            started.append({"worker": name, "status": "completed", "result": result})
            continue
        log_path = worker_log_path(args, name)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_handle:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--run-root-base",
                    args.run_root_base,
                    "--worktree-root-base",
                    args.worktree_root_base,
                    "--lease-root",
                    args.lease_root,
                    "--run-tag",
                    args.run_tag,
                    "worker-runner",
                    "--worker",
                    name,
                    "--phase",
                    phase,
                    "--trial-id",
                    trial_id,
                    "--budget-minutes",
                    str(budget),
                    *([] if simulate_metric is None else ["--simulate-metric", str(simulate_metric)]),
                    *([] if simulate_delay_seconds <= 0 else ["--simulate-delay-seconds", str(simulate_delay_seconds)]),
                ],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        with file_lock(lock_path(args)):
            latest = load_state(args)
            update_worker_status(latest, name, status="running", pid=proc.pid, trial_id=trial_id, note=f"{phase} running")
            save_state(args, latest)
        started.append({"worker": name, "status": "started", "pid": proc.pid, "trial_id": trial_id})
    return {"ok": True, "command": phase, "workers": started, "budget_minutes": budget}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def contained_path(root: Path, relative_path: str, label: str) -> Path:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise AutoresearchV2Error(f"{label} escapes its allowed root: {relative_path}") from exc
    return candidate


def expand_runtime_value(value: str, runtime_values: dict[str, str]) -> str:
    expanded = value
    for key, replacement in runtime_values.items():
        expanded = expanded.replace("${" + key + "}", replacement)
    return expanded


def input_record(worker_root: Path, declared_path: str) -> dict[str, Any]:
    path = contained_path(worker_root, declared_path, "provenance input")
    if not path.exists():
        raise AutoresearchV2Error(f"declared provenance input does not exist: {declared_path}")
    if path.is_file():
        return {"path": declared_path, "kind": "file", "size": path.stat().st_size, "sha256": sha256_file(path)}
    if not path.is_dir():
        raise AutoresearchV2Error(f"unsupported provenance input type: {declared_path}")
    files: list[dict[str, Any]] = []
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        resolved = child.resolve()
        try:
            resolved.relative_to(worker_root.resolve())
        except ValueError as exc:
            raise AutoresearchV2Error(f"provenance input symlink escapes worker root: {child}") from exc
        files.append({"path": resolved.relative_to(worker_root.resolve()).as_posix(), "size": resolved.stat().st_size, "sha256": sha256_file(resolved)})
    aggregate = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"path": declared_path, "kind": "directory", "sha256": aggregate, "files": files}


def environment_summary(environment: dict[str, str], runtime_keys: list[str]) -> dict[str, Any]:
    declared = {key: hashlib.sha256(value.encode("utf-8")).hexdigest() for key, value in sorted(environment.items())}
    return {"declared_value_sha256": declared, "runtime_keys": sorted(runtime_keys)}


def collect_declared_artifacts(worker_root: Path, run_dir: Path, patterns: list[str]) -> list[dict[str, Any]]:
    destination_root = run_dir / "declared_artifacts"
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in patterns:
        normalized = pattern.replace("\\", "/")
        if normalized.startswith("/") or ".." in Path(normalized).parts:
            raise AutoresearchV2Error(f"artifact pattern escapes worker root: {pattern}")
        for source in sorted(worker_root.glob(normalized)):
            if not source.is_file():
                continue
            resolved = source.resolve()
            try:
                relative = resolved.relative_to(worker_root.resolve())
            except ValueError as exc:
                raise AutoresearchV2Error(f"artifact symlink escapes worker root: {source}") from exc
            relative_text = relative.as_posix()
            if relative_text in seen:
                continue
            seen.add(relative_text)
            destination = destination_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolved, destination)
            records.append({"path": relative_text, "archive_path": destination.relative_to(run_dir).as_posix(), "size": destination.stat().st_size, "sha256": sha256_file(destination)})
    return records


def run_process_tree(command: list[str], cwd: Path, env: dict[str, str], log_path: Path, timeout_seconds: int) -> tuple[int | None, bool]:
    with log_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log_handle, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=timeout_seconds), False
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                try:
                    import psutil

                    psutil_available = True
                except ImportError:
                    psutil_available = False
                if psutil_available:
                    try:
                        root_process = psutil.Process(process.pid)
                        descendants = root_process.children(recursive=True)
                        for descendant in reversed(descendants):
                            descendant.kill()
                        root_process.kill()
                        psutil.wait_procs([*descendants, root_process], timeout=5)
                    except psutil.Error:
                        psutil_available = False
                if not psutil_available:
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=10,
                        check=False,
                    )
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)
            return None, True


def measure_metric(state: dict[str, Any], run_dir: Path, simulate_metric: float | None) -> tuple[float, dict[str, Any]]:
    results_dir = (run_dir / "results").resolve()
    metric_path = contained_path(results_dir, str(state["target"]["metric"]["path"]), "metric.path")
    if simulate_metric is not None:
        write_json(metric_path, {"primary_metric": float(simulate_metric)})
    if not metric_path.is_file():
        raise AutoresearchV2Error(f"metrics file was not created: {metric_path}")
    payload = json.loads(metric_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AutoresearchV2Error("metrics file must contain a JSON object")
    value = payload.get("primary_metric")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise AutoresearchV2Error("primary_metric must be a finite JSON number")
    optional = payload.get("metrics", {})
    if optional is None:
        optional = {}
    if not isinstance(optional, dict):
        raise AutoresearchV2Error("metrics must be a mapping when provided")
    normalized_metrics: dict[str, float] = {}
    for key, item in optional.items():
        if not isinstance(key, str) or not key:
            raise AutoresearchV2Error("metrics keys must be non-empty strings")
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
            raise AutoresearchV2Error(f"metrics.{key} must be a finite JSON number")
        normalized_metrics[key] = float(item)
    normalized: dict[str, Any] = {"primary_metric": float(value)}
    if normalized_metrics:
        normalized["metrics"] = normalized_metrics
    return float(value), normalized


def trial_is_logged(path: Path, trial_id: str) -> bool:
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return False
    header = lines[0].split("\t")
    if "trial_id" not in header:
        return False
    index = header.index("trial_id")
    return any(len(row := line.split("\t")) > index and row[index] == trial_id for line in lines[1:])


def record_trial_outcome(args: argparse.Namespace, outcome: dict[str, Any]) -> None:
    run_dir = Path(str(outcome["run_dir"]))
    outcome_path = run_dir / "outcome.json"
    authoritative = outcome
    if outcome_path.exists():
        existing = read_json(outcome_path, {})
        if existing != outcome:
            raise AutoresearchV2Error(f"conflicting outcome already exists for trial_id {outcome['trial_id']}")
        authoritative = existing
    else:
        write_json(outcome_path, outcome)
    trial_id = str(authoritative["trial_id"])
    if not trial_is_logged(results_path(args), trial_id):
        append_results_row(results_path(args), authoritative)


def build_trial_outcome(
    *,
    worker: str,
    phase: str,
    trial_id: str,
    branch: str,
    commit: str,
    metric: float | None,
    best_metric_before: float | None,
    delta: float | str,
    decision: str,
    completion_reason: str,
    process_exit_code: int | None,
    metric_extracted: bool,
    error_type: str,
    timed_out: bool,
    budget_minutes: int,
    run_dir: Path,
    notes: str,
) -> dict[str, Any]:
    return {
        "timestamp": utc_now(),
        "worker": worker,
        "phase": phase,
        "trial_id": trial_id,
        "branch": branch,
        "commit": commit,
        "metric": metric,
        "best_metric_before": best_metric_before,
        "delta": delta,
        "decision": decision,
        "completion_reason": completion_reason,
        "process_exit_code": process_exit_code,
        "metric_extracted": metric_extracted,
        "error_type": error_type,
        "timed_out": timed_out,
        "budget_minutes": budget_minutes,
        "run_dir": str(run_dir),
        "notes": notes,
    }


def run_worker_once(
    args: argparse.Namespace,
    *,
    worker: str,
    phase: str,
    trial_id: str,
    budget_minutes: int,
    simulate_metric: float | None,
    simulate_delay_seconds: float,
) -> dict[str, Any]:
    state = ensure_initialized(args)
    entry = state["workers"][worker]
    worker_root = Path(entry["worktree"])
    run_dir = worker_artifact_root(args, worker) / trial_id
    run_output_dir = run_dir / "run_output"
    run_results_dir = run_dir / "results"
    run_output_dir.mkdir(parents=True, exist_ok=True)
    run_results_dir.mkdir(parents=True, exist_ok=True)
    head_commit = git_head(worker_root)
    branch = current_branch(worker_root)

    lease = None
    selected_gpu = ""
    artifact_records: list[dict[str, Any]] = []
    completion_reason = "completed"
    process_exit_code: int | None = None
    timed_out = False
    metric_extracted = False
    metric_payload: dict[str, Any] = {}
    try:
        gpu_policy = str(state["target"]["gpu"].get("mode") or "none")
        selector = str(state["target"]["gpu"].get("selector") or "0")
        wait_seconds = int(state["target"]["gpu"].get("max_wait_seconds") or 0)
        if gpu_policy == "lease":
            lease = acquire_gpu_lease(
                Path(args.lease_root),
                selector=selector,
                owner=f"{args.run_tag}:{worker}:{trial_id}",
                wait_seconds=wait_seconds,
            )
            selected_gpu = str(lease["gpu"])
        target = state["target"]
        runtime_values = {
            "AR2_WORKER_ROOT": str(worker_root),
            "AR2_RUN_DIR": str(run_dir),
            "AR2_OUTPUT_DIR": str(run_output_dir),
            "AR2_RESULTS_DIR": str(run_results_dir),
            "AR2_BUDGET_MINUTES": str(budget_minutes),
        }
        if lease is not None:
            runtime_values["AR2_GPU_ID"] = selected_gpu
        declared_env = {str(key): expand_runtime_value(str(value), runtime_values) for key, value in dict(target["run"].get("env") or {}).items()}
        command = [expand_runtime_value(str(token), runtime_values) for token in list(target["run"]["argv"])]
        unresolved = [value for value in command + list(declared_env.values()) if "${AR2_" in value]
        if unresolved:
            raise AutoresearchV2Error(f"unavailable runtime placeholder in target: {unresolved[0]}")
        env = os.environ.copy()
        env.update(declared_env)
        env.update(runtime_values)
        cwd = contained_path(worker_root, str(target["run"].get("cwd") or "."), "run.cwd")
        if not cwd.is_dir():
            raise AutoresearchV2Error(f"run.cwd is not a directory: {cwd}")
        input_records = [input_record(worker_root, path) for path in list(target.get("provenance", {}).get("inputs") or [])]
        runtime_files = [Path(__file__).resolve(), Path(__file__).with_name("autoresearch_v2_common.py")]
        provenance = {
            "schema_version": 2,
            "created_at": utc_now(),
            "program": {"path": state["program_snapshot"], "sha256": sha256_file(Path(state["program_snapshot"]))},
            "target": {"path": state["target_snapshot"], "sha256": sha256_file(Path(state["target_snapshot"]))},
            "source": {"commit": head_commit, "status": git(worker_root, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()},
            "command": {"argv": command, "cwd": str(cwd)},
            "environment": environment_summary(declared_env, list(runtime_values)),
            "inputs": input_records,
            "runtime": [{"name": path.name, "sha256": sha256_file(path)} for path in runtime_files],
            "resource": {"mode": gpu_policy, **({"id": selected_gpu} if lease is not None else {})},
        }
        write_json(run_dir / "provenance.json", provenance)
        write_json(run_dir / "command.json", {"argv": command, "cwd": str(cwd)})
        append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "run_started", "worker": worker, "trial_id": trial_id, "phase": phase})

        if simulate_metric is None:
            process_exit_code, timed_out = run_process_tree(command, cwd, env, run_dir / "process.log", max(budget_minutes, 1) * 60)
            if timed_out:
                completion_reason = "timeout"
                raise AutoresearchV2Error("worker command timed out")
            if process_exit_code != 0:
                completion_reason = "process_error"
                raise AutoresearchV2Error(f"worker command failed with exit code {process_exit_code}")

        if simulate_metric is not None and simulate_delay_seconds > 0:
            time.sleep(simulate_delay_seconds)

        try:
            metric, metric_payload = measure_metric(state, run_dir, simulate_metric)
            metric_extracted = True
            append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "metric_recorded", "worker": worker, "trial_id": trial_id, "primary_metric": metric})
            artifact_records = collect_declared_artifacts(worker_root, run_dir, list(target.get("artifacts") or []))
            for artifact in artifact_records:
                append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "artifact_recorded", "worker": worker, "trial_id": trial_id, **artifact})
            write_json(run_dir / "execution.json", {"exit_code": process_exit_code, "timed_out": timed_out, "primary_metric": metric, "metrics": metric_payload.get("metrics", {}), "artifacts": artifact_records})
        except Exception:
            if not timed_out:
                completion_reason = "metric_error"
            raise

        with file_lock(lock_path(args)):
            latest = load_state(args)
            if phase == "baseline" and latest.get("baseline") is not None:
                raise AutoresearchV2Error("baseline already exists for this run")
            if phase != "baseline" and latest.get("baseline") is None:
                raise AutoresearchV2Error("baseline must be established before run or resume")
            best_metric_before = latest.get("best_metric")
            best_commit_before = str(latest.get("best_commit") or "")
            threshold = float(latest.get("keep_threshold") or 0.0)
            direction = str(latest["program"]["direction"])
            if phase == "baseline":
                keep = True
            elif direction == "higher":
                keep = metric > float(best_metric_before) + threshold
            else:
                keep = metric < float(best_metric_before) - threshold
            decision = "keep" if keep else "discard"
            delta = "" if best_metric_before is None else metric - float(best_metric_before)
            if keep:
                latest["best_metric"] = metric
                latest["best_commit"] = head_commit
                git(Path(latest["repo_root"]), "branch", "-f", latest["best_branch"], head_commit)
                if phase == "baseline":
                    latest["baseline"] = {"metric": metric, "commit": head_commit, "worker": worker, "trial_id": trial_id}
                status_name = "kept"
                retained_commit = head_commit
            else:
                reset_worktree(worker_root, best_commit_before)
                status_name = "discarded"
                retained_commit = git_head(worker_root)
            outcome = build_trial_outcome(
                worker=worker,
                phase=phase,
                trial_id=trial_id,
                branch=branch,
                commit=head_commit,
                metric=metric,
                best_metric_before=best_metric_before,
                delta=delta,
                decision=decision,
                completion_reason=completion_reason,
                process_exit_code=process_exit_code,
                metric_extracted=metric_extracted,
                error_type="",
                timed_out=timed_out,
                budget_minutes=budget_minutes,
                run_dir=run_dir,
                notes="resource lease used" if lease is not None else "",
            )
            update_worker_status(
                latest,
                str(outcome["worker"]),
                status=status_name,
                last_metric=outcome["metric"],
                last_decision=str(outcome["decision"]),
                last_commit=retained_commit,
                last_run_dir=str(outcome["run_dir"]),
                trial_id=str(outcome["trial_id"]),
                trial_commit=str(outcome["commit"]),
                run_dir=str(outcome["run_dir"]),
                completion_reason=str(outcome["completion_reason"]),
                process_exit_code=outcome["process_exit_code"],
                metric_extracted=bool(outcome["metric_extracted"]),
                gpu=selected_gpu,
                note=f"{outcome['phase']} {outcome['decision']}",
            )
            record_trial_outcome(args, outcome)
            save_state(args, latest)
        append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "run_finished", "worker": worker, "trial_id": trial_id, "decision": decision, "completion_reason": completion_reason})
        return {
            "ok": True,
            "worker": worker,
            "phase": phase,
            "trial_id": trial_id,
            "metric": metric,
            "decision": decision,
            "commit": head_commit,
            "run_dir": str(run_dir),
            "metric_payload": metric_payload,
        }
    except Exception as exc:
        with file_lock(lock_path(args)):
            latest = load_state(args)
            best_metric_before = latest.get("best_metric")
            best_commit = str(latest.get("best_commit") or "")
            cleanup_error = ""
            retained_commit = head_commit
            if best_commit:
                try:
                    reset_worktree(worker_root, best_commit)
                    retained_commit = git_head(worker_root)
                except Exception as cleanup_exc:
                    cleanup_error = f"; reset_failed={cleanup_exc}"
            error_type = type(exc).__name__
            if completion_reason == "completed":
                completion_reason = "process_error"
            outcome = build_trial_outcome(
                worker=worker,
                phase=phase,
                trial_id=trial_id,
                branch=branch,
                commit=head_commit,
                metric=None,
                best_metric_before=best_metric_before,
                delta="",
                decision="crash",
                completion_reason=completion_reason,
                process_exit_code=process_exit_code,
                metric_extracted=metric_extracted,
                error_type=error_type,
                timed_out=timed_out,
                budget_minutes=budget_minutes,
                run_dir=run_dir,
                notes=str(exc) + cleanup_error,
            )
            outcome["traceback"] = traceback.format_exc()
            update_worker_status(
                latest,
                str(outcome["worker"]),
                status="failed",
                last_decision=str(outcome["decision"]),
                last_commit=retained_commit,
                last_run_dir=str(outcome["run_dir"]),
                trial_id=str(outcome["trial_id"]),
                trial_commit=str(outcome["commit"]),
                run_dir=str(outcome["run_dir"]),
                completion_reason=str(outcome["completion_reason"]),
                process_exit_code=outcome["process_exit_code"],
                metric_extracted=bool(outcome["metric_extracted"]),
                gpu=selected_gpu,
                note=str(outcome["notes"]),
            )
            record_trial_outcome(args, outcome)
            save_state(args, latest)
        append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "run_finished", "worker": worker, "trial_id": trial_id, "decision": "crash", "completion_reason": completion_reason, "error_type": type(exc).__name__})
        raise
    finally:
        if lease is not None:
            release_gpu_lease(Path(args.lease_root), str(lease.get("gpu") or ""))
        with file_lock(lock_path(args)):
            latest = load_state(args)
            worker_status = latest["workers"][worker]["status"]
            if worker_status not in {"kept", "discarded", "failed"}:
                update_worker_status(latest, worker, status="idle", pid=None, note="idle")
                save_state(args, latest)
            elif latest["workers"][worker].get("gpu"):
                update_worker_status(latest, worker, status=worker_status, gpu="")
                save_state(args, latest)


def status(args: argparse.Namespace) -> dict[str, Any]:
    with file_lock(lock_path(args)):
        state = ensure_initialized(args)
        for worker, entry in state["workers"].items():
            pid = entry.get("pid")
            if entry["status"] == "running" and not is_pid_running(pid):
                update_worker_status(state, worker, status="stopped", pid=None, note="runner pid not alive")
        save_state(args, state)
    return {
        "ok": True,
        "command": "status",
        "run_tag": state["run_tag"],
        "best_metric": state.get("best_metric"),
        "best_commit": state.get("best_commit"),
        "baseline": state.get("baseline"),
        "workers": state["workers"],
    }


def stop(args: argparse.Namespace) -> dict[str, Any]:
    state = ensure_initialized(args)
    workers = selected_workers(state, getattr(args, "worker", None), getattr(args, "all_workers", False))
    stopped = []
    with file_lock(lock_path(args)):
        latest = load_state(args)
        for worker in workers:
            pid = latest["workers"][worker].get("pid")
            killed = terminate_pid(pid)
            update_worker_status(latest, worker, status="stopped", pid=None, note="stopped by operator")
            gpu = str(latest["workers"][worker].get("gpu") or "")
            if gpu:
                release_gpu_lease(Path(args.lease_root), gpu)
            stopped.append({"worker": worker, "pid": pid, "killed": killed})
        save_state(args, latest)
    return {"ok": True, "command": "stop", "workers": stopped}


def sync_best(args: argparse.Namespace) -> dict[str, Any]:
    state = ensure_initialized(args)
    workers = selected_workers(state, getattr(args, "worker", None), getattr(args, "all_workers", False))
    synced = []
    with file_lock(lock_path(args)):
        latest = load_state(args)
        best_commit = str(latest.get("best_commit") or "")
        for worker in workers:
            entry = latest["workers"][worker]
            if is_pid_running(entry.get("pid")):
                synced.append({"worker": worker, "status": "running"})
                continue
            reset_worktree(Path(entry["worktree"]), best_commit)
            commit = git_head(Path(entry["worktree"]))
            update_worker_status(latest, worker, status="idle", last_commit=commit, note="synced to best")
            synced.append({"worker": worker, "status": "synced", "commit": commit})
        save_state(args, latest)
    return {"ok": True, "command": "sync-best", "workers": synced, "best_commit": state.get("best_commit")}


def collect(args: argparse.Namespace) -> dict[str, Any]:
    state = ensure_initialized(args)
    payload = {
        "ok": True,
        "command": "collect",
        "run_root": str(run_root(args)),
        "results_path": str(results_path(args)),
        "events_path": str(events_path(args)),
        "leaderboard_path": str(leaderboard_path(args)),
        "state_path": str(state_path(args)),
    }
    return payload


def doctor_check(name: str, ok: bool, detail: str, *, required: bool = True) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "required": required, "detail": detail}


def writable_directory_check(name: str, path: Path) -> dict[str, Any]:
    probe = path / f".autoresearch-doctor-{os.getpid()}.tmp"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
        return doctor_check(name, True, str(path))
    except Exception as exc:
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
        return doctor_check(name, False, f"{path}: {exc}")


def doctor(args: argparse.Namespace) -> dict[str, Any]:
    root = run_root(args)
    checks: list[dict[str, Any]] = []
    python_path = Path(sys.executable)
    checks.append(
        doctor_check(
            "python_executable",
            python_path.is_file() and os.access(python_path, os.X_OK),
            str(python_path),
        )
    )
    git_executable = shutil.which("git")
    git_ok = False
    git_detail = git_executable or "git was not found on PATH"
    if git_executable:
        completed = subprocess.run(
            [git_executable, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        git_ok = completed.returncode == 0
        git_detail = (completed.stdout or completed.stderr or git_executable).strip()
    checks.append(doctor_check("git_executable", git_ok, git_detail))
    checks.extend(
        [
            writable_directory_check("run_root_writable", root),
            writable_directory_check("worktree_root_writable", Path(args.worktree_root_base)),
            writable_directory_check("lease_root_writable", Path(args.lease_root)),
        ]
    )
    module_root = Path(__file__).resolve().parent
    required_modules = [
        "autoresearch_v2_common.py",
        "autoresearch_v2_gpu_lease.py",
    ]
    missing_modules = [name for name in required_modules if not (module_root / name).is_file()]
    checks.append(
        doctor_check(
            "bridge_modules",
            not missing_modules,
            "all required modules present" if not missing_modules else "missing: " + ", ".join(missing_modules),
        )
    )
    target_repo: Path | None = None
    target_source = "not provided"
    if args.target:
        target = load_target_spec(Path(args.target))
        target_repo = Path(target["repo"]["path"])
        target_source = str(Path(args.target))
    elif state_path(args).exists():
        existing_state = read_json(state_path(args), {})
        if isinstance(existing_state, dict) and existing_state.get("repo_root"):
            target_repo = Path(str(existing_state["repo_root"]))
            target_source = str(state_path(args))
    if target_repo is None:
        checks.append(doctor_check("target_repo", True, "not checked: no target or initialized state", required=False))
    else:
        repo_check = (
            git(target_repo, "rev-parse", "--is-inside-work-tree", check=False)
            if git_ok and target_repo.exists()
            else None
        )
        repo_ok = bool(repo_check and repo_check.returncode == 0 and repo_check.stdout.strip() == "true")
        checks.append(doctor_check("target_repo", repo_ok, f"{target_repo} (from {target_source})"))
    ok = all(check["ok"] for check in checks if check["required"])
    payload = {
        "ok": ok,
        "command": "doctor",
        "run_root": str(root),
        "worktree_root_base": str(Path(args.worktree_root_base)),
        "lease_root": str(Path(args.lease_root)),
        "python": sys.executable,
        "checks": checks,
    }
    return payload


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "doctor":
        return doctor(args)
    if args.command == "bootstrap":
        return bootstrap(args)
    if args.command == "inspect":
        return inspect_worker(args)
    if args.command == "apply":
        return apply_overlay(args)
    if args.command == "baseline":
        return launch_workers(
            args,
            phase="baseline",
            worker=args.worker,
            all_workers=False,
            budget_minutes=args.budget_minutes,
            simulate_metric=args.simulate_metric,
            simulate_delay_seconds=args.simulate_delay_seconds,
            foreground=args.foreground,
        )
    if args.command == "run":
        return launch_workers(
            args,
            phase="run",
            worker=args.worker,
            all_workers=args.all_workers,
            budget_minutes=args.budget_minutes,
            simulate_metric=args.simulate_metric,
            simulate_delay_seconds=args.simulate_delay_seconds,
            foreground=args.foreground,
        )
    if args.command == "resume":
        return launch_workers(
            args,
            phase="run",
            worker=args.worker,
            all_workers=args.all_workers,
            budget_minutes=args.budget_minutes,
            simulate_metric=args.simulate_metric,
            simulate_delay_seconds=args.simulate_delay_seconds,
            foreground=args.foreground,
        )
    if args.command == "status":
        return status(args)
    if args.command == "stop":
        return stop(args)
    if args.command == "sync-best":
        return sync_best(args)
    if args.command == "collect":
        return collect(args)
    if args.command == "worker-runner":
        result = run_worker_once(
            args,
            worker=args.worker,
            phase=args.phase,
            trial_id=args.trial_id,
            budget_minutes=args.budget_minutes,
            simulate_metric=args.simulate_metric,
            simulate_delay_seconds=args.simulate_delay_seconds,
        )
        return result
    raise AutoresearchV2Error(f"unsupported command: {args.command}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    ensure_run_tag(args.run_tag)
    payload = dispatch(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok", False) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "error_type": type(exc).__name__},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from exc
