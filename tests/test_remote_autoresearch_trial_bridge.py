from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOTE_CONFIG = PROJECT_ROOT / "config" / "remote.example.psd1"
TRIAL_CONFIG = PROJECT_ROOT / "config" / "autoresearch-train.example.psd1"
SUBMIT_TRIAL = PROJECT_ROOT / "scripts" / "remote" / "submit-autoresearch-trial.ps1"
SYNC_CODE = PROJECT_ROOT / "scripts" / "remote" / "sync-code.ps1"
FETCH_RESULTS = PROJECT_ROOT / "scripts" / "remote" / "fetch-results.ps1"
DEPLOY_REMOTE_BIN = PROJECT_ROOT / "scripts" / "remote" / "deploy-remote-bin.ps1"
RUN_LOCAL_CHECKS = PROJECT_ROOT / "scripts" / "remote" / "run-local-checks.ps1"
RUN_TRIAL = PROJECT_ROOT / "scripts" / "remote" / "remote-bin" / "run_autoresearch_trial.sh"
REMOTE_COMMON = PROJECT_ROOT / "scripts" / "remote" / "lib" / "common.ps1"
REMOTE_README = PROJECT_ROOT / "scripts" / "remote" / "README.md"
REMOTE_DOCTOR = PROJECT_ROOT / "scripts" / "remote" / "doctor.ps1"


class RemoteAutoresearchTrialBridgeTest(unittest.TestCase):
    def test_remote_config_declares_trial_entrypoint(self) -> None:
        remote_config = REMOTE_CONFIG.read_text(encoding="utf-8")
        common = REMOTE_COMMON.read_text(encoding="utf-8")

        for text in (remote_config, common):
            self.assertIn("RemoteAutoresearchTrialEntry", text)
            self.assertIn("run_autoresearch_trial.sh", text)
            self.assertNotIn("/home/cgv841/", text)

    def test_remote_doctor_checks_fixed_entrypoints(self) -> None:
        doctor = REMOTE_DOCTOR.read_text(encoding="utf-8")

        self.assertIn("RemoteAutoresearchTrialEntry", doctor)
        self.assertIn("remote_entrypoints_exist", doctor)
        self.assertIn("test -x", doctor)
        self.assertRegex(doctor, r"\$coreOk\s*=.*remote_entrypoints_exist")
        self.assertIn("codex_proxy_ok", doctor)

    def test_trial_parameter_config_is_karpathy_style_bounded(self) -> None:
        config = TRIAL_CONFIG.read_text(encoding="utf-8")

        self.assertIn("MetricName = 'mAP'", config)
        self.assertIn("Direction = 'higher'", config)
        self.assertIn("MaxSeconds = 300", config)
        self.assertIn("SmokeBatches = 1", config)
        self.assertIn("AllowFullTraining = $false", config)

    def test_submit_trial_uses_fixed_remote_entry_and_not_full_training(self) -> None:
        script = SUBMIT_TRIAL.read_text(encoding="utf-8")

        self.assertIn("RemoteAutoresearchTrialEntry", script)
        self.assertIn("Get-TrialConfig", script)
        self.assertIn("--max-seconds", script)
        self.assertIn("--smoke-batches", script)
        self.assertIn("DryRun", script)
        self.assertNotIn("RemoteTrainEntry", script)
        self.assertNotIn("ConfirmFullTraining", script)
        self.assertNotIn("submit-job.ps1", script)

    def test_submit_trial_has_hard_parameter_caps(self) -> None:
        script = SUBMIT_TRIAL.read_text(encoding="utf-8")

        self.assertIn("$effectiveSmokeBatches -gt 10", script)
        self.assertIn("SmokeBatches must be between 1 and 10 inclusive", script)
        self.assertIn("$effectiveMaxSeconds -gt 3600", script)
        self.assertIn("MaxSeconds must be between 1 and 3600 inclusive", script)

    def test_sync_code_uses_path_boundary_check(self) -> None:
        script = SYNC_CODE.read_text(encoding="utf-8")

        self.assertIn("Test-IsPathAtOrUnder", script)
        self.assertIn("$rootWithSeparator", script)
        self.assertNotIn(".StartsWith($resolvedProject", script)

    def test_fetch_results_keeps_explicit_optional_whitelist(self) -> None:
        script = FETCH_RESULTS.read_text(encoding="utf-8")

        for target in ("metrics.json", "summary.json", "config_used.yaml", "logs", "error_samples"):
            self.assertIn(f'"{target}"', script)
        self.assertIn("test -e", script)
        self.assertIn("Invoke-RemoteScpFrom", script)

    def test_local_remote_static_check_runs_without_remote_access(self) -> None:
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
        self.assertTrue(report["ok"])
        check_names = {check["name"] for check in report["checks"]}
        self.assertIn("experiment_id_regex_consistent", check_names)
        self.assertIn("trial_smoke_batches_upper_bound", check_names)
        self.assertIn("trial_max_seconds_upper_bound", check_names)
        self.assertIn("sync_code_uses_path_boundary_check", check_names)

    def test_remote_trial_is_bounded_and_non_tmux(self) -> None:
        script = RUN_TRIAL.read_text(encoding="utf-8")

        self.assertIn("SCRIPT_NAME=\"run_autoresearch_trial.sh\"", script)
        self.assertIn("MODE=\"trial\"", script)
        self.assertIn("timeout --foreground", script)
        self.assertIn("--smoke-batches", script)
        self.assertIn("write_last_metric", script)
        self.assertNotIn("tmux new-session", script)
        self.assertNotIn("--confirm-full-training", script)

    def test_remote_bin_deploy_is_fixed_to_project_entrypoints(self) -> None:
        script = DEPLOY_REMOTE_BIN.read_text(encoding="utf-8")

        self.assertIn("remote-bin", script)
        self.assertIn("RemoteWorkspaceRoot", script)
        self.assertIn("Invoke-RemoteScpTo", script)
        self.assertIn("chmod 700", script)
        self.assertNotIn("Remove-Item", script)
        self.assertNotIn("submit-job.ps1", script)

    def test_remote_readme_names_trial_bridge_contract(self) -> None:
        readme = REMOTE_README.read_text(encoding="utf-8")

        self.assertIn("submit-autoresearch-trial.ps1", readme)
        self.assertIn("deploy-remote-bin.ps1", readme)
        self.assertIn("bounded Karpathy-style trial", readme)
        self.assertIn("config/autoresearch-train.local.psd1", readme)


if __name__ == "__main__":
    unittest.main()
