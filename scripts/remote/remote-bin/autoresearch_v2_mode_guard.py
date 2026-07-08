#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any


def default_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def normalize_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def path_in_scope(path: str, patterns: list[str]) -> bool:
    normalized = normalize_path(path)
    candidate = PurePosixPath(normalized)
    for raw_pattern in patterns:
        pattern = normalize_path(raw_pattern)
        if not pattern:
            continue
        if pattern.endswith("/**"):
            base = pattern[:-3].rstrip("/")
            if normalized == base or normalized.startswith(f"{base}/"):
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
        if any(candidate.match(item) or fnmatch.fnmatch(normalized, item) for item in variants):
            return True
    return False


def load_policy(project_root: Path) -> dict[str, Any]:
    policy_path = project_root / ".codex" / "research-policy.json"
    with policy_path.open("r", encoding="utf-8") as handle:
        policy = json.load(handle)
    autoresearch = policy.get("autoresearch")
    if not isinstance(autoresearch, dict):
        raise ValueError("research-policy.json is missing autoresearch policy.")
    return autoresearch


def git_changed_files(project_root: Path) -> list[str]:
    files: set[str] = set()
    commands = [
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
    ]
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            files.update(line.strip() for line in completed.stdout.splitlines() if line.strip())
    return sorted(files)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guard autoresearch v2 development/invocation mode boundaries.")
    parser.add_argument("--project-root", default=str(default_project_root()))
    parser.add_argument("--mode", choices=["invoke", "develop"], default="")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--stdin", action="store_true", help="Read newline-delimited changed files from stdin.")
    parser.add_argument("--from-git", action="store_true", help="Read changed files from git diff and staged diff.")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    project_root = Path(args.project_root).resolve()
    policy = load_policy(project_root)
    mode = args.mode or str(policy.get("default_mode") or "invoke")
    modes = policy.get("modes") or {}
    mode_policy = modes.get(mode)
    if not isinstance(mode_policy, dict):
        raise ValueError(f"unknown autoresearch mode: {mode}")

    changed = list(args.changed_file)
    if args.stdin:
        changed.extend(line.strip() for line in sys.stdin if line.strip())
    if args.from_git:
        changed.extend(git_changed_files(project_root))
    changed = sorted({normalize_path(item) for item in changed if item.strip()})

    sealed_paths = [str(item) for item in policy.get("sealed_paths") or []]
    may_modify_sealed = bool(mode_policy.get("may_modify_sealed_paths"))
    violations = [
        path for path in changed
        if (not may_modify_sealed) and path_in_scope(path, sealed_paths)
    ]

    payload = {
        "ok": not violations,
        "mode": mode,
        "project_root": str(project_root),
        "changed_files": changed,
        "sealed_paths": sealed_paths,
        "violations": violations,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if violations:
            print("autoresearch mode guard failed")
            print(f"mode: {mode}")
            print("sealed path modifications:")
            for path in violations:
                print(f"- {path}")
        else:
            print(f"autoresearch mode guard passed ({mode})")
    return 0 if not violations else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc
