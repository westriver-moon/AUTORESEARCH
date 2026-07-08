#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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
    render_command,
    replace_tokens,
    reset_worktree,
    terminate_pid,
    utc_now,
    worker_name,
    write_json,
)
from autoresearch_v2_gpu_lease import acquire_gpu_lease, release_gpu_lease
from autoresearch_v2_metric_tvilfm import parse_tvilfm_metric, prepare_tvilfm_config


SCHEMA_VERSION = "autoresearch-v2"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remote-first autoresearch v2 controller")
    parser.add_argument("--run-root-base", required=True)
    parser.add_argument("--worktree-root-base", required=True)
    parser.add_argument("--lease-root", required=True)
    parser.add_argument("--run-tag", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor")

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
    budget_mode = str(state["program"]["budget_mode"])
    budgets = dict(state["target"]["run"].get("budget_minutes") or {})
    return int(budgets.get(budget_mode) or budgets.get("medium") or 30)


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
    if root.exists() and not args.force:
        raise AutoresearchV2Error(f"run root already exists: {root}")
    root.mkdir(parents=True, exist_ok=True)

    program_path = Path(args.program)
    target_path = Path(args.target)
    program = load_program_spec(program_path)
    target = load_target_spec(target_path)
    if program["direction"] != target["run"]["metric"]["direction"]:
        raise AutoresearchV2Error("program.direction must match target.run.metric.direction")

    spec_dir = root / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    program_snapshot = spec_dir / "program.md"
    target_snapshot = spec_dir / "target.yaml"
    shutil.copy2(program_path, program_snapshot)
    shutil.copy2(target_path, target_snapshot)

    repo_root = Path(target["repo"]["remote_root"])
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
    append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "bootstrap", "run_tag": args.run_tag})
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
    append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "inspect", "worker": worker, "file_count": len(copied)})
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
    append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "apply", "worker": worker, "changed": changed})
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
    append_jsonl(events_path(args), {"timestamp": utc_now(), "event": phase, "started": started})
    return {"ok": True, "command": phase, "workers": started, "budget_minutes": budget}


def measure_metric(state: dict[str, Any], run_dir: Path, run_output_dir: Path, simulate_metric: float | None) -> tuple[float, dict[str, Any]]:
    primary_key = str(state["target"]["run"]["metric"]["primary_key"])
    if simulate_metric is not None:
        payload = {
            "available": True,
            "schema_version": "simulated-metric-v1",
            "primary_metric": float(simulate_metric),
            primary_key: float(simulate_metric),
        }
        write_json(run_dir / "results" / "metrics.json", payload)
        return float(simulate_metric), payload

    parser_name = str(state["target"]["run"]["metric"]["parser"])
    results_dir = run_dir / "results"
    if parser_name == "tvilfm_reid":
        payload = parse_tvilfm_metric(run_output_dir, results_dir)
    elif parser_name == "json_file":
        metric_file = results_dir / str(state["target"]["run"]["metric"]["path"])
        payload = json.loads(metric_file.read_text(encoding="utf-8"))
    else:
        raise AutoresearchV2Error(f"unsupported metric parser: {parser_name}")
    if not payload.get("available", True):
        raise AutoresearchV2Error(f"metric parser reported unavailable metric: {payload}")
    if primary_key not in payload:
        raise AutoresearchV2Error(f"metric payload is missing primary key {primary_key!r}")
    return float(payload[primary_key]), payload


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
    try:
        gpu_policy = str(state["target"]["gpu"].get("policy") or "none")
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
        else:
            selected_gpu = selector

        if simulate_metric is None:
            target = state["target"]
            training = dict(target.get("training") or {})
            env = os.environ.copy()
            env.update({str(key): str(value) for key, value in dict(target["run"].get("environment") or {}).items()})
            python_bin = training.get("python_bin") or sys.executable
            prepared_config_path = run_dir / "config_used.yaml"
            source_config = Path(training.get("config_path") or "")
            if target["run"]["metric"]["parser"] == "tvilfm_reid":
                prepare_tvilfm_config(
                    source_config=source_config,
                    destination_config=prepared_config_path,
                    run_output_dir=run_output_dir,
                    data_root=str(training.get("data_root") or ""),
                    pretrained=str(training.get("pretrained") or ""),
                    gpu=selected_gpu or "0",
                )
            mapping = {
                "python_bin": python_bin,
                "config_path": str(source_config),
                "prepared_config_path": str(prepared_config_path),
                "worker_root": str(worker_root),
                "repo_root": str(worker_root),
                "run_dir": str(run_dir),
                "run_output_dir": str(run_output_dir),
                "run_results_dir": str(run_results_dir),
                "budget_minutes": budget_minutes,
                "gpu": selected_gpu,
            }
            command = render_command(list(target["run"]["command"]), mapping)
            env["CUDA_VISIBLE_DEVICES"] = selected_gpu
            env["AR2_RUN_DIR"] = str(run_dir)
            env["AR2_RUN_OUTPUT_DIR"] = str(run_output_dir)
            env["AR2_RESULTS_DIR"] = str(run_results_dir)
            env["AR2_BUDGET_MINUTES"] = str(budget_minutes)
            cwd = worker_root / str(target["run"].get("cwd") or ".")
            with (run_dir / "command.json").open("w", encoding="utf-8") as handle:
                json.dump({"command": command, "cwd": str(cwd)}, handle, ensure_ascii=False, indent=2)
            with (run_dir / "process.log").open("w", encoding="utf-8") as log_handle:
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    timeout=max(budget_minutes, 1) * 60,
                    check=False,
                    text=True,
                )
            if completed.returncode != 0:
                raise AutoresearchV2Error(f"worker command failed with exit code {completed.returncode}")

        if simulate_metric is not None and simulate_delay_seconds > 0:
            time.sleep(simulate_delay_seconds)

        metric, metric_payload = measure_metric(state, run_dir, run_output_dir, simulate_metric)

        with file_lock(lock_path(args)):
            latest = load_state(args)
            best_metric_before = latest.get("best_metric")
            best_commit_before = str(latest.get("best_commit") or "")
            threshold = float(latest.get("keep_threshold") or 0.0)
            direction = str(latest["program"]["direction"])
            keep = False
            if best_metric_before is None or phase == "baseline":
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
                if latest.get("baseline") is None:
                    latest["baseline"] = {"metric": metric, "commit": head_commit, "worker": worker, "trial_id": trial_id}
                status_name = "kept"
                retained_commit = head_commit
            else:
                reset_worktree(worker_root, best_commit_before)
                status_name = "discarded"
                retained_commit = git_head(worker_root)
            update_worker_status(
                latest,
                worker,
                status=status_name,
                last_metric=metric,
                last_decision=decision,
                last_commit=retained_commit,
                last_run_dir=str(run_dir),
                trial_id=trial_id,
                gpu=selected_gpu,
                note=f"{phase} {decision}",
            )
            save_state(args, latest)
            append_results_row(
                results_path(args),
                {
                    "timestamp": utc_now(),
                    "worker": worker,
                    "phase": phase,
                    "branch": branch,
                    "commit": head_commit,
                    "metric": metric,
                    "best_metric_before": best_metric_before,
                    "delta": delta,
                    "decision": decision,
                    "budget_minutes": budget_minutes,
                    "run_dir": str(run_dir),
                    "notes": f"gpu={selected_gpu}",
                },
            )
            append_jsonl(
                events_path(args),
                {
                    "timestamp": utc_now(),
                    "event": "worker-finished",
                    "worker": worker,
                    "phase": phase,
                    "trial_id": trial_id,
                    "metric": metric,
                    "decision": decision,
                    "commit": head_commit,
                    "best_metric_before": best_metric_before,
                },
            )
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
            update_worker_status(
                latest,
                worker,
                status="failed",
                last_commit=head_commit,
                last_run_dir=str(run_dir),
                trial_id=trial_id,
                gpu=selected_gpu,
                note=str(exc),
            )
            save_state(args, latest)
            append_jsonl(
                events_path(args),
                {
                    "timestamp": utc_now(),
                    "event": "worker-failed",
                    "worker": worker,
                    "phase": phase,
                    "trial_id": trial_id,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
        raise
    finally:
        if lease is not None:
            release_gpu_lease(Path(args.lease_root), str(lease.get("gpu") or ""))
        with file_lock(lock_path(args)):
            latest = load_state(args)
            if latest["workers"][worker]["status"] not in {"kept", "discarded", "failed"}:
                update_worker_status(latest, worker, status="idle", pid=None, note="idle")
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
    append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "stop", "workers": stopped})
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
    append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "sync-best", "workers": synced})
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
    append_jsonl(events_path(args), {"timestamp": utc_now(), "event": "collect"})
    return payload


def doctor(args: argparse.Namespace) -> dict[str, Any]:
    root = run_root(args)
    payload = {
        "ok": True,
        "command": "doctor",
        "run_root": str(root),
        "worktree_root_base": str(Path(args.worktree_root_base)),
        "lease_root": str(Path(args.lease_root)),
        "git_available": shutil.which("git") is not None,
        "python": sys.executable,
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
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AutoresearchV2Error as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc
