from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from .base import SCRIPTS_DIR, AutoresearchScriptsTestBase

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_skill_invariants import (  # noqa: E402
    read_text_with_encoding_fallback,
    validate_exec_event_log,
)


class SkillInvariantTests(AutoresearchScriptsTestBase):
    def test_event_log_reader_accepts_powershell_utf16_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('{"type":"turn.completed"}\n', encoding="utf-16")

            self.assertIn("turn.completed", read_text_with_encoding_fallback(path))

    def test_event_log_helper_match_accepts_windows_json_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                "\n".join(
                    [
                        r'{"command":"python C:\\Users\\me\\.codex\\skills\\codex-autoresearch\\scripts\\autoresearch_init_run.py"}',
                        r'{"command":"python C:\\Users\\me\\.codex\\skills\\codex-autoresearch\\scripts\\autoresearch_record_iteration.py"}',
                        r'{"command":"python C:\\Users\\me\\.codex\\skills\\codex-autoresearch\\scripts\\autoresearch_exec_state.py"}',
                    ]
                ),
                encoding="utf-16",
            )

            validate_exec_event_log(path)
