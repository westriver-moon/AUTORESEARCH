from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / ".codex" / "research-policy.json"
GUARD = PROJECT_ROOT / "scripts" / "remote" / "remote-bin" / "autoresearch_v2_mode_guard.py"
INVOKE_SKILL = PROJECT_ROOT / ".agents" / "skills" / "codex-autoresearch-v2" / "SKILL.md"
DEV_SKILL = PROJECT_ROOT / ".agents" / "skills" / "codex-autoresearch-v2-dev" / "SKILL.md"
PLUGIN_ROOT = PROJECT_ROOT / "plugins" / "codex-autoresearch-v2"
GIT_HOOK = PROJECT_ROOT / ".githooks" / "pre-commit"
LEGACY_SKILL = PROJECT_ROOT / ".agents" / "skills" / "codex-autoresearch"
LEGACY_AUDIT = PROJECT_ROOT / ".agents" / "audit" / "codex-autoresearch-legacy"


class AutoresearchV2ModePolicyTest(unittest.TestCase):
    def run_guard(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GUARD), *args, "--json"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_policy_declares_invoke_and_develop_modes(self) -> None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        autoresearch = policy["autoresearch"]

        self.assertEqual(autoresearch["default_mode"], "invoke")
        self.assertEqual(autoresearch["modes"]["invoke"]["skill_path"], ".agents/skills/codex-autoresearch-v2")
        self.assertEqual(autoresearch["modes"]["develop"]["skill_path"], ".agents/skills/codex-autoresearch-v2-dev")
        self.assertEqual(autoresearch["git_hook_entrypoint"], ".githooks/pre-commit")
        self.assertFalse(autoresearch["modes"]["invoke"]["may_modify_sealed_paths"])
        self.assertTrue(autoresearch["modes"]["develop"]["may_modify_sealed_paths"])
        self.assertIn(".agents/skills/codex-autoresearch-v2/**", autoresearch["sealed_paths"])

    def test_skills_route_invocation_and_development_modes(self) -> None:
        invoke_text = INVOKE_SKILL.read_text(encoding="utf-8")
        dev_text = DEV_SKILL.read_text(encoding="utf-8")

        self.assertIn("Use this skill in invocation mode.", invoke_text)
        self.assertIn("$codex-autoresearch-v2-dev", invoke_text)
        self.assertIn("Use this skill in development mode", dev_text)
        self.assertIn("Development mode may edit these paths", dev_text)

    def test_pre_commit_hook_uses_mode_guard(self) -> None:
        hook_text = GIT_HOOK.read_text(encoding="utf-8")

        self.assertIn("AUTORESEARCH_MODE:-invoke", hook_text)
        self.assertIn("autoresearch_v2_mode_guard.py", hook_text)
        self.assertIn("--stdin", hook_text)

    def test_invoke_mode_rejects_sealed_paths(self) -> None:
        completed = self.run_guard(
            "--mode",
            "invoke",
            "--changed-file",
            ".agents/skills/codex-autoresearch-v2/SKILL.md",
        )

        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["violations"], [".agents/skills/codex-autoresearch-v2/SKILL.md"])

    def test_develop_mode_allows_sealed_paths(self) -> None:
        completed = self.run_guard(
            "--mode",
            "develop",
            "--changed-file",
            ".agents/skills/codex-autoresearch-v2/SKILL.md",
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["violations"], [])

    def test_invoke_mode_allows_run_inputs(self) -> None:
        completed = self.run_guard(
            "--mode",
            "invoke",
            "--changed-file",
            "autoresearch/program.md",
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["violations"], [])

    def test_versioned_plugin_package_contains_invoke_skill_and_runtime(self) -> None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        plugin = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        contract = json.loads((PLUGIN_ROOT / "assets" / "readonly-contract.json").read_text(encoding="utf-8"))

        self.assertEqual(plugin["name"], "codex-autoresearch-v2")
        self.assertEqual(plugin["version"], policy["autoresearch"]["packaged_plugin"]["version"])
        self.assertEqual(contract["version"], plugin["version"])
        self.assertEqual(contract["mode"], "invoke")
        self.assertTrue((PLUGIN_ROOT / "skills" / "codex-autoresearch-v2" / "SKILL.md").exists())
        self.assertTrue((PLUGIN_ROOT / "scripts" / "remote" / "autoresearch-v2.ps1").exists())
        self.assertTrue((PLUGIN_ROOT / "scripts" / "remote" / "smoke-autoresearch-v2.ps1").exists())
        self.assertTrue((PLUGIN_ROOT / "scripts" / "remote" / "guard-autoresearch-mode.ps1").exists())
        self.assertTrue((PLUGIN_ROOT / "scripts" / "remote" / "lib" / "common.ps1").exists())
        self.assertTrue((PLUGIN_ROOT / "scripts" / "remote" / "lib" / "ssh.ps1").exists())
        self.assertTrue((PLUGIN_ROOT / "scripts" / "remote" / "lib" / "result.ps1").exists())
        self.assertTrue((PLUGIN_ROOT / "scripts" / "remote" / "lib" / "autoresearch_v2.ps1").exists())

    def test_legacy_skill_is_not_discoverable(self) -> None:
        self.assertFalse(LEGACY_SKILL.exists())
        self.assertTrue((LEGACY_AUDIT / "SKILL.md").exists())
        self.assertTrue(INVOKE_SKILL.exists())
        self.assertTrue(DEV_SKILL.exists())


if __name__ == "__main__":
    unittest.main()
