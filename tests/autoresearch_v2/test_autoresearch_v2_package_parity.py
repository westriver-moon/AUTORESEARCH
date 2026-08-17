from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from support import PROJECT_ROOT

PLUGIN_ROOT = PROJECT_ROOT / "plugins" / "codex-autoresearch-v2"
PACKAGE_SCRIPT = PROJECT_ROOT / "scripts" / "package-autoresearch-v2-plugin.ps1"


class AutoresearchV2PackageParityTest(unittest.TestCase):
    def assert_tree_matches(self, actual_root: Path, expected_root: Path) -> None:
        actual_files = sorted(path.relative_to(actual_root) for path in actual_root.rglob("*") if path.is_file())
        expected_files = sorted(path.relative_to(expected_root) for path in expected_root.rglob("*") if path.is_file())
        self.assertEqual(actual_files, expected_files)
        for relative in actual_files:
            with self.subTest(relative=relative.as_posix()):
                self.assertEqual(
                    (actual_root / relative).read_bytes(),
                    (expected_root / relative).read_bytes(),
                )

    def test_committed_plugin_is_generated_from_canonical_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            generated = Path(temporary) / "codex-autoresearch-v2"
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(PACKAGE_SCRIPT),
                    "-OutputPath",
                    str(generated),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assert_tree_matches(PLUGIN_ROOT, generated)

            packaged_paths = {path.relative_to(generated).as_posix() for path in generated.rglob("*") if path.is_file()}
            self.assertNotIn("assets/autoresearch-v2.local.psd1", packaged_paths)
            self.assertFalse(any("__pycache__" in path for path in packaged_paths))
            self.assertFalse(any(path.endswith("README.md") for path in packaged_paths))


if __name__ == "__main__":
    unittest.main()
