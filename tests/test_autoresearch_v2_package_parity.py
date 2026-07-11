from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = PROJECT_ROOT / "plugins" / "codex-autoresearch-v2"


class AutoresearchV2PackageParityTest(unittest.TestCase):
    def assert_tree_matches(self, packaged_root: Path, source_root: Path) -> None:
        packaged_files = sorted(path.relative_to(packaged_root) for path in packaged_root.rglob("*") if path.is_file())
        self.assertTrue(packaged_files, packaged_root)
        for relative in packaged_files:
            with self.subTest(relative=relative.as_posix()):
                packaged = packaged_root / relative
                source = source_root / relative
                self.assertTrue(source.is_file(), source)
                self.assertEqual(packaged.read_bytes(), source.read_bytes())

    def test_packaged_runtime_matches_repository_runtime(self) -> None:
        self.assert_tree_matches(
            PLUGIN_ROOT / "scripts" / "remote",
            PROJECT_ROOT / "scripts" / "remote",
        )

    def test_packaged_invoke_skill_matches_repository_skill(self) -> None:
        self.assert_tree_matches(
            PLUGIN_ROOT / "skills" / "codex-autoresearch-v2",
            PROJECT_ROOT / ".agents" / "skills" / "codex-autoresearch-v2",
        )


if __name__ == "__main__":
    unittest.main()
