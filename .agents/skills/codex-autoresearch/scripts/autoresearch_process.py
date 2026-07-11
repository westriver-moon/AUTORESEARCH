from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def decode_output(value: bytes | str | None, *, encoding: str = "utf-8") -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode(encoding, errors="replace")


def run_text(
    args: list[str] | tuple[str, ...],
    *,
    input: str | bytes | None = None,
    encoding: str = "utf-8",
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    kwargs.pop("text", None)
    kwargs.pop("encoding", None)
    kwargs.pop("errors", None)
    if isinstance(input, str):
        input_value: bytes | None = input.encode(encoding)
    else:
        input_value = input
    completed = subprocess.run(
        args,
        input=input_value,
        text=False,
        **kwargs,
    )
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        decode_output(completed.stdout, encoding=encoding),
        decode_output(completed.stderr, encoding=encoding),
    )


def popen_text(
    args: list[str] | tuple[str, ...],
    *,
    encoding: str = "utf-8",
    **kwargs: Any,
) -> subprocess.Popen[str]:
    kwargs.pop("text", None)
    kwargs.pop("encoding", None)
    kwargs.pop("errors", None)
    return subprocess.Popen(
        args,
        text=True,
        encoding=encoding,
        errors="replace",
        **kwargs,
    )


def _path_exts() -> list[str]:
    raw = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD") if os.name == "nt" else ""
    return [item.lower() for item in raw.split(os.pathsep) if item.strip()]


def _executable_candidates(name: str) -> list[str]:
    suffix = Path(name).suffix.lower()
    exts = _path_exts()
    if os.name != "nt":
        return [name]
    if suffix in exts:
        return [name]
    return [f"{name}{ext}" for ext in exts]


def find_executable(name: str) -> Path | None:
    if not name.strip():
        return None
    candidate = Path(name)
    has_path = candidate.is_absolute() or "/" in name or "\\" in name
    if has_path:
        for executable_name in _executable_candidates(str(candidate)):
            executable = Path(executable_name)
            if executable.is_file() and (os.name == "nt" or os.access(executable, os.X_OK)):
                return executable.resolve()
        return None

    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    for directory in path_parts:
        if not directory:
            continue
        for executable_name in _executable_candidates(name):
            executable = Path(directory) / executable_name
            if executable.is_file() and (os.name == "nt" or os.access(executable, os.X_OK)):
                return executable.resolve()
    return None


def pid_is_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            int(pid),
        )
        if not handle:
            return False
        exit_code = wintypes.DWORD()
        try:
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _run_ps(pid: int, field: str) -> str | None:
    completed = run_text(
        ["ps", "-p", str(pid), "-o", f"{field}="],
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def inspect_process_identity(pid: int | None) -> dict[str, object] | None:
    if pid is None or pid <= 0 or not pid_is_alive(pid):
        return None
    if os.name == "nt":
        return {
            "pid": pid,
            "pgid": pid,
            "started_at": "windows-process",
            "command": "windows-process",
        }

    pgid_text = _run_ps(pid, "pgid")
    started_at = _run_ps(pid, "lstart")
    command = _run_ps(pid, "command")
    if pgid_text is None or started_at is None or command is None:
        return {
            "pid": pid,
            "pgid": os.getpgid(pid),
            "started_at": "",
            "command": "",
        }
    try:
        pgid = int(pgid_text)
    except ValueError:
        pgid = os.getpgid(pid)
    return {
        "pid": pid,
        "pgid": pgid,
        "started_at": started_at,
        "command": command,
    }


def process_group_id(pid: int) -> int:
    if os.name == "nt":
        return pid
    return os.getpgid(pid)


def terminate_process_tree(pid: int | None, *, pgid: int | None = None, kill: bool = False) -> None:
    if pid is None or pid <= 0:
        return
    if os.name == "nt":
        args = ["taskkill", "/PID", str(pid), "/T"]
        if kill:
            args.append("/F")
        subprocess.run(args, capture_output=True, text=True, errors="replace", check=False)
        return

    target_pgid = pgid or os.getpgid(pid)
    sig = signal.SIGKILL if kill else signal.SIGTERM
    try:
        os.killpg(int(target_pgid), sig)
    except ProcessLookupError:
        return


def wait_for_exit(pid: int | None, *, timeout: float, poll_interval: float = 0.1) -> bool:
    if not pid_is_alive(pid):
        return True
    deadline = time.time() + max(timeout, 0.0)
    while time.time() < deadline:
        time.sleep(poll_interval)
        if not pid_is_alive(pid):
            return True
    return not pid_is_alive(pid)
