from __future__ import annotations

import json
import subprocess
import unittest

from support import PROJECT_ROOT

ROOT_README = PROJECT_ROOT / "README.md"
REMOTE_README = PROJECT_ROOT / "scripts" / "remote" / "README.md"
POLICY_PATH = PROJECT_ROOT / ".codex" / "research-policy.json"
RUN_LOCAL_CHECKS = PROJECT_ROOT / "scripts" / "remote" / "run-local-checks.ps1"


class AutoresearchV2ProjectContractTest(unittest.TestCase):
    def test_readmes_point_to_v2_runtime(self) -> None:
        root_readme = ROOT_README.read_text(encoding="utf-8")
        remote_readme = REMOTE_README.read_text(encoding="utf-8")

        self.assertIn("scripts/remote/autoresearch-v2.ps1", root_readme)
        self.assertIn(".agents/skills/codex-autoresearch-v2/", root_readme)
        self.assertIn("autoresearch-v2.ps1", remote_readme)
        self.assertIn("smoke-autoresearch-v2.ps1", remote_readme)

    def test_research_policy_lists_current_remote_entrypoints(self) -> None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            policy["training"]["allowed_entrypoints"],
            [
                "scripts/remote/autoresearch-v2.ps1",
                "scripts/remote/smoke-autoresearch-v2.ps1",
            ],
        )

    def test_run_local_checks_reports_current_contract(self) -> None:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(RUN_LOCAL_CHECKS),
                "-Json",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )

        report = json.loads(completed.stdout)
        checks = {check["name"]: check for check in report["checks"]}
        self.assertEqual(report["script"], "run-local-checks.ps1")
        self.assertTrue(checks["v2_modes_declared"]["ok"])
        self.assertTrue(checks["v2_remote_roots_declared"]["ok"])
        self.assertTrue(checks["generic_remote_support_declared"]["ok"])
        self.assertTrue(checks["remote_access_layer_owned"]["ok"])
        self.assertTrue(checks["autoresearch_modes_declared"]["ok"])
        self.assertTrue(checks["invoke_skill_is_sealed"]["ok"])
        self.assertTrue(checks["dev_skill_declares_development_mode"]["ok"])
        self.assertTrue(checks["v2_plugin_packaged"]["ok"])


if __name__ == "__main__":
    unittest.main()
