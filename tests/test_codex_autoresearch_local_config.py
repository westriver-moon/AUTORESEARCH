from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "autoresearch.example.psd1"
DOCTOR_PATH = PROJECT_ROOT / "scripts" / "autoresearch" / "doctor.ps1"
SCRIPT_README = PROJECT_ROOT / "scripts" / "autoresearch" / "README.md"
ROOT_README = PROJECT_ROOT / "README.md"


class CodexAutoresearchLocalConfigTest(unittest.TestCase):
    def test_example_config_keeps_project_policy_restricted(self) -> None:
        config = CONFIG_PATH.read_text(encoding="utf-8")

        self.assertIn("Invocation = 'explicit_only'", config)
        self.assertIn("SessionMode = 'foreground'", config)
        self.assertIn("PythonCommand = 'python'", config)
        self.assertIn("RequireGitRepo = $true", config)
        self.assertIn("AllowControlledRemoteTrialBridge = $true", config)
        self.assertIn("AllowFullTrainingFromAutoresearch = $false", config)

        for key in (
            "AllowImplicitInvocation",
            "AllowBackground",
            "AllowExec",
            "AllowHooks",
            "AllowFullAccessBypass",
            "AllowDangerouslyBypassApprovalsAndSandbox",
            "AllowSshDuringSkillLaunch",
            "AllowGpuDuringSkillLaunch",
        ):
            self.assertIn(f"{key} = $false", config)

        self.assertIn("'launch.json'", config)
        self.assertIn("'runtime.json'", config)
        self.assertIn("'runtime.log'", config)

    def test_doctor_is_read_only_and_does_not_call_disabled_paths(self) -> None:
        script = DOCTOR_PATH.read_text(encoding="utf-8")

        forbidden_snippets = (
            "autoresearch_runtime_ctl.py",
            "autoresearch_hooks_ctl.py install",
            'FileName = "codex"',
            "Start-Process codex",
            "--dangerously-bypass-approvals-and-sandbox",
            "ssh.exe",
            "submit-job.ps1",
            "ConfirmFullTraining",
        )
        for snippet in forbidden_snippets:
            self.assertNotIn(snippet, script)

        self.assertIn("Get-GitRepoRoot", script)
        self.assertIn("ConvertTo-Json", script)

    def test_doctor_reports_current_adapter_state_as_json(self) -> None:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(DOCTOR_PATH),
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

        self.assertEqual(report["script"], "autoresearch-doctor")
        self.assertTrue(checks["skill_exists"]["ok"])
        self.assertFalse(checks["vendor_exists"]["required"])
        self.assertEqual(checks["vendor_exists"]["severity"], "info")
        self.assertTrue(checks["lock_exists"]["ok"])
        self.assertTrue(checks["trial_config_exists"]["ok"])
        self.assertTrue(checks["trial_submit_script_exists"]["ok"])
        self.assertTrue(checks["trial_remote_entry_exists"]["ok"])
        self.assertTrue(checks["explicit_invocation_policy"]["ok"])
        self.assertTrue(checks["foreground_only_policy"]["ok"])
        self.assertTrue(checks["exec_disabled_policy"]["ok"])
        self.assertTrue(checks["hooks_disabled_policy"]["ok"])
        self.assertTrue(checks["local_policy_is_restricted"]["ok"])

        if report["git_root"]:
            self.assertTrue(checks["project_is_git_repo"]["ok"])
        else:
            self.assertFalse(checks["project_is_git_repo"]["ok"])
            self.assertFalse(report["ok"])

    def test_docs_explain_adapter_contract_and_doctor(self) -> None:
        script_readme = SCRIPT_README.read_text(encoding="utf-8")
        root_readme = ROOT_README.read_text(encoding="utf-8")

        for text in (script_readme, root_readme):
            self.assertIn("foreground", text)
            self.assertIn("doctor.ps1 -Json", text)
            self.assertIn("codex exec", text)
            self.assertIn("SSH", text)
            self.assertIn("vendor", text)
            self.assertIn("informational", text)

    def test_skill_documents_controlled_trial_bridge(self) -> None:
        skill_md = (PROJECT_ROOT / ".agents" / "skills" / "codex-autoresearch" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Karpathy-style remote GPU trials are the only exception", skill_md)
        self.assertIn("scripts\\remote\\submit-autoresearch-trial.ps1", skill_md)
        self.assertIn("Do not compose arbitrary SSH commands", skill_md)
        self.assertIn("full training remains a separate human-confirmed action", skill_md)


if __name__ == "__main__":
    unittest.main()
