from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOTE_CONFIG = PROJECT_ROOT / "config" / "remote.example.psd1"
TRIAL_CONFIG = PROJECT_ROOT / "config" / "autoresearch-train.example.psd1"
SUBMIT_TRIAL = PROJECT_ROOT / "scripts" / "remote" / "submit-autoresearch-trial.ps1"
DEPLOY_REMOTE_BIN = PROJECT_ROOT / "scripts" / "remote" / "deploy-remote-bin.ps1"
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
