from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .base import SCRIPTS_DIR, AutoresearchScriptsTestBase

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from autoresearch_process import (  # noqa: E402
    decode_output,
    find_executable,
    inspect_process_identity,
    pid_is_alive,
    popen_text,
    run_text,
)


class ProcessCompatTests(AutoresearchScriptsTestBase):
    def test_decode_output_replaces_invalid_bytes(self) -> None:
        text = decode_output(b"ok:\xff\n")

        self.assertIn("ok:", text)
        self.assertIn("\ufffd", text)

    def test_run_text_decodes_invalid_child_output_without_raising(self) -> None:
        completed = run_text(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'ok:\\xff\\n')",
            ],
            capture_output=True,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("ok:", completed.stdout)
        self.assertIn("\ufffd", completed.stdout)

    def test_popen_text_decodes_invalid_child_output_without_reader_thread_errors(self) -> None:
        process = popen_text(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'ok:\\xff\\n')",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(timeout=10)

        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn("ok:", stdout)
        self.assertIn("\ufffd", stdout)

    def test_find_executable_uses_pathext_for_windows_command_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample-tool").write_text("extensionless shim\n", encoding="utf-8")
            command = root / "sample-tool.CMD"
            command.write_text("@echo off\n", encoding="utf-8")
            old_path = os.environ.get("PATH", "")
            old_pathext = os.environ.get("PATHEXT", "")
            try:
                os.environ["PATH"] = str(root)
                os.environ["PATHEXT"] = ".COM;.EXE;.BAT;.CMD"
                self.assertEqual(find_executable("sample-tool"), command)
            finally:
                os.environ["PATH"] = old_path
                os.environ["PATHEXT"] = old_pathext

    def test_pid_helpers_use_cross_platform_python_process_checks(self) -> None:
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertTrue(pid_is_alive(process.pid))
            identity = inspect_process_identity(process.pid)
            self.assertIsNotNone(identity)
            self.assertEqual(identity["pid"], process.pid)
            self.assertIn("command", identity)
        finally:
            process.terminate()
            process.wait(timeout=10)

        self.assertFalse(pid_is_alive(process.pid))
