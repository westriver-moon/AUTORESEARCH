from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOTE_CONFIG = PROJECT_ROOT / "config" / "remote.example.psd1"
TRIAL_CONFIG = PROJECT_ROOT / "config" / "autoresearch-train.example.psd1"
SUBMIT_TRIAL = PROJECT_ROOT / "scripts" / "remote" / "submit-autoresearch-trial.ps1"
SUBMIT_SMOKE = PROJECT_ROOT / "scripts" / "remote" / "submit-smoke-test.ps1"
SUBMIT_JOB = PROJECT_ROOT / "scripts" / "remote" / "submit-job.ps1"
CHECK_JOB = PROJECT_ROOT / "scripts" / "remote" / "check-job.ps1"
REMOTE_CHECK_JOB = PROJECT_ROOT / "scripts" / "remote" / "remote-bin" / "check_job.sh"
SYNC_CODE = PROJECT_ROOT / "scripts" / "remote" / "sync-code.ps1"
FETCH_RESULTS = PROJECT_ROOT / "scripts" / "remote" / "fetch-results.ps1"
DEPLOY_REMOTE_BIN = PROJECT_ROOT / "scripts" / "remote" / "deploy-remote-bin.ps1"
RUN_LOCAL_CHECKS = PROJECT_ROOT / "scripts" / "remote" / "run-local-checks.ps1"
TRAINING_LIB = PROJECT_ROOT / "scripts" / "remote" / "lib" / "training.ps1"
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

        self.assertIn("RunTag = 'ar_tvilfm_pmtvit_stagea_trial'", config)
        self.assertIn("MetricName = 'mAP'", config)
        self.assertIn("Direction = 'higher'", config)
        self.assertIn("TVI-LFM", config)
        self.assertIn("pmt_vit_stage_a_pmt_recipe_288x144_768.yaml", config)
        self.assertIn("MaxSeconds = 300", config)
        self.assertIn("SmokeBatches = 1", config)
        self.assertIn("Gpu = 'auto'", config)
        self.assertIn("AllowFullTraining = $false", config)

    def test_remote_shell_default_config_matches_tvilfm_trial_target(self) -> None:
        common = (PROJECT_ROOT / "scripts" / "remote" / "remote-bin" / "researchops_common.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("TVI-LFM", common)
        self.assertIn("pmt_vit_stage_a_pmt_recipe_288x144_768.yaml", common)
        self.assertNotIn("DEFAULT_PROJECT_ROOT=\"${PROJECT_ROOT:-${REMOTE_ROOT}/PMT-SYSU}\"", common)
        self.assertNotIn("pmt_sysu/config", common)

    def test_remote_shell_can_select_idle_gpu(self) -> None:
        common = (PROJECT_ROOT / "scripts" / "remote" / "remote-bin" / "researchops_common.sh").read_text(
            encoding="utf-8"
        )
        training_lib = TRAINING_LIB.read_text(encoding="utf-8")

        self.assertIn("resolve_gpu", common)
        self.assertIn("nvidia-smi", common)
        self.assertIn("memory.used <= 1024 MiB", common)
        self.assertIn("utilization.gpu <= 10%", common)
        self.assertIn('($effectiveGpu.ToLowerInvariant() -ne "auto")', training_lib)

    def test_remote_shell_writes_normalized_reid_metrics(self) -> None:
        common = (PROJECT_ROOT / "scripts" / "remote" / "remote-bin" / "researchops_common.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("reid-metrics-v1", common)
        self.assertIn("primary_metric", common)
        self.assertIn("primary_metric_source", common)
        self.assertIn('"metric_name": "mAP"', common)
        self.assertIn("rank1_percent", common)
        self.assertIn("best_mAP", common)
        self.assertIn("raw_block", common)

    def test_submit_trial_uses_fixed_remote_entry_and_not_full_training(self) -> None:
        script = SUBMIT_TRIAL.read_text(encoding="utf-8")

        self.assertIn("RemoteAutoresearchTrialEntry", script)
        self.assertIn("Get-TrainingConfig", script)
        self.assertIn("--max-seconds", script)
        self.assertIn("--smoke-batches", script)
        self.assertIn("selected_gpu", script)
        self.assertIn("DryRun", script)
        self.assertNotIn("RemoteTrainEntry", script)
        self.assertNotIn("ConfirmFullTraining", script)
        self.assertNotIn("submit-job.ps1", script)

    def test_remote_root_is_exported_for_entrypoint_commands(self) -> None:
        training_lib = TRAINING_LIB.read_text(encoding="utf-8")

        self.assertIn("Add-RemoteRootExport", training_lib)
        self.assertIn("REMOTE_ROOT=", training_lib)
        self.assertIn("export REMOTE_ROOT", training_lib)

        for path in (SUBMIT_TRIAL, SUBMIT_SMOKE, SUBMIT_JOB, CHECK_JOB, PROJECT_ROOT / "scripts" / "remote" / "cancel-own-job.ps1"):
            script = path.read_text(encoding="utf-8")
            self.assertIn("Add-RemoteRootExport", script)

    def test_smoke_and_full_train_reuse_autoresearch_training_config(self) -> None:
        smoke = SUBMIT_SMOKE.read_text(encoding="utf-8")
        full = SUBMIT_JOB.read_text(encoding="utf-8")

        for script in (smoke, full):
            self.assertIn("Get-TrainingConfig", script)
            self.assertIn("Add-TrainingRemoteArgs", script)

        training_lib = TRAINING_LIB.read_text(encoding="utf-8")
        for arg_name in ("project-root", "python", "data-root", "config", "pretrained", "gpu"):
            self.assertIn(f'-Name "{arg_name}"', training_lib)

        self.assertIn("--smoke-batches", smoke)
        self.assertIn("--max-seconds", smoke)
        self.assertIn("--confirm-full-training", full)
        self.assertIn("Full training requires -ConfirmFullTraining.", full)
        self.assertIn("selected_gpu", smoke)
        self.assertIn("selected_gpu", full)

    def test_check_job_not_found_remains_failure(self) -> None:
        local = CHECK_JOB.read_text(encoding="utf-8")
        remote = REMOTE_CHECK_JOB.read_text(encoding="utf-8")

        self.assertIn("remote_state", local)
        self.assertIn('"not_found"', local)
        self.assertIn('sys.exit(1 if data.get("state") == "not_found" else 0)', remote)

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
        self.assertIn('$ok = ($fetched.Count -gt 0)', script)
        self.assertIn("no_result_files_fetched", script)

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
        self.assertIn("autoresearch_trial_defaults_to_tvilfm_pmt_vit", check_names)
        self.assertIn("autoresearch_trial_supports_auto_gpu", check_names)
        self.assertIn("autoresearch_trial_writes_reid_metrics_json", check_names)
        self.assertIn("remote_entrypoints_use_tvilfm_main", check_names)
        self.assertIn("sync_code_uses_path_boundary_check", check_names)

    def test_remote_trial_is_bounded_and_non_tmux(self) -> None:
        script = RUN_TRIAL.read_text(encoding="utf-8")

        self.assertIn("SCRIPT_NAME=\"run_autoresearch_trial.sh\"", script)
        self.assertIn("MODE=\"trial\"", script)
        self.assertIn("timeout --foreground", script)
        self.assertIn("main.py", script)
        self.assertIn("--config_select", script)
        self.assertIn("--smoke-batches", script)
        self.assertIn("resolve_gpu", script)
        self.assertIn("write_last_metric", script)
        self.assertNotIn("pmt_sysu.train", script)
        self.assertNotIn("tmux new-session", script)
        self.assertNotIn("--confirm-full-training", script)

    def test_remote_smoke_and_train_use_tvilfm_main(self) -> None:
        for path in (
            PROJECT_ROOT / "scripts" / "remote" / "remote-bin" / "run_smoke_test.sh",
            PROJECT_ROOT / "scripts" / "remote" / "remote-bin" / "run_train.sh",
        ):
            script = path.read_text(encoding="utf-8")
            self.assertIn("main.py", script)
            self.assertIn("--config_select", script)
            self.assertIn("prepare_tvilfm_config", script)
            self.assertNotIn("pmt_sysu.train", script)

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
