from __future__ import annotations

import csv
import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import types
import unittest
from pathlib import Path
from unittest import mock

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DRIVER = PROJECT_ROOT / "scripts" / "remote" / "remote-bin" / "autoresearch_v2_driver.py"


def load_driver_module():
    driver_dir = DRIVER.parent
    if str(driver_dir) not in sys.path:
        sys.path.insert(0, str(driver_dir))
    spec = importlib.util.spec_from_file_location("autoresearch_v2_driver_test", DRIVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RemoteAutoresearchV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo = self.root / "repo"
        self.repo.mkdir(parents=True, exist_ok=True)
        (self.repo / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.repo / "sleep_metric.py").write_text(
            textwrap.dedent(
                """
                import json
                import os
                import sys
                import time
                from pathlib import Path

                out_dir = Path(sys.argv[1])
                metric_name = sys.argv[2]
                sleep_seconds = float(os.environ.get("AR_TEST_SLEEP", "0"))
                time.sleep(sleep_seconds)
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / metric_name).write_text(
                    json.dumps({"available": True, "primary_metric": 0.42}, ensure_ascii=False),
                    encoding="utf-8",
                )
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self._git("init")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test User")
        self._git("add", ".")
        self._git("commit", "-m", "initial")
        self._git("branch", "-M", "main")

        self.program = self.root / "program.md"
        self.program.write_text(
            textwrap.dedent(
                """
                ---
                goal: Test remote-first autoresearch
                metric: primary_metric
                direction: higher
                budget_mode: short
                worker_count: 2
                keep_threshold: 0.0
                mutable_paths:
                  - model.py
                ---

                # Test Program
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        self.target = self.root / "target.yaml"
        self.target.write_text(
            yaml.safe_dump(
                {
                    "name": "unit-target",
                    "repo": {
                        "remote_root": str(self.repo),
                        "base_ref": "main",
                        "mutable_paths": ["model.py"],
                    },
                    "run": {
                        "cwd": ".",
                        "command": ["python", "sleep_metric.py", "{run_results_dir}", "metric.json"],
                        "budget_minutes": {"short": 1, "medium": 1, "long": 1},
                        "metric": {
                            "parser": "json_file",
                            "direction": "higher",
                            "path": "metric.json",
                            "primary_key": "primary_metric",
                        },
                        "environment": {"AR_TEST_SLEEP": "8"},
                    },
                    "gpu": {"policy": "none", "selector": "0", "max_wait_seconds": 0},
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        self.run_root_base = self.root / "runs"
        self.worktree_root_base = self.root / "worktrees"
        self.lease_root = self.root / "leases"
        self.run_tag = "unit-run"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed:\n{completed.stdout}\n{completed.stderr}")
        return completed

    def run_driver(self, *command: str, expect_ok: bool = True) -> dict:
        completed = self.run_driver_process(*command)
        if expect_ok and completed.returncode != 0:
            raise AssertionError(f"driver failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
        payload = json.loads(completed.stdout)
        if expect_ok:
            self.assertTrue(payload["ok"], payload)
        return payload

    def run_driver_process(self, *command: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.driver_argv(*command),
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def driver_argv(self, *command: str) -> list[str]:
        return [
            "python",
            str(DRIVER),
            "--run-root-base",
            str(self.run_root_base),
            "--worktree-root-base",
            str(self.worktree_root_base),
            "--lease-root",
            str(self.lease_root),
            "--run-tag",
            self.run_tag,
            *command,
        ]

    def bootstrap(self, *, target: Path | None = None, workers: int = 1) -> dict:
        return self.run_driver(
            "bootstrap",
            "--program",
            str(self.program),
            "--target",
            str(target or self.target),
            "--branch-prefix",
            "autoresearch/",
            "--worker-count",
            str(workers),
        )

    def run_timeout_trial(self, *, trial_id: str, phase: str, metric: float | None):
        driver = load_driver_module()
        args = driver.build_parser().parse_args(
            [
                "--run-root-base",
                str(self.run_root_base),
                "--worktree-root-base",
                str(self.worktree_root_base),
                "--lease-root",
                str(self.lease_root),
                "--run-tag",
                self.run_tag,
                "worker-runner",
                "--worker",
                "w1",
                "--phase",
                phase,
                "--trial-id",
                trial_id,
                "--budget-minutes",
                "1",
            ]
        )
        run_dir = driver.worker_artifact_root(args, "w1") / trial_id
        if metric is not None:
            result_dir = run_dir / "results"
            result_dir.mkdir(parents=True, exist_ok=True)
            (result_dir / "metric.json").write_text(
                json.dumps({"available": True, "primary_metric": metric}),
                encoding="utf-8",
            )
        real_subprocess = driver.subprocess

        def raise_timeout(*_args, **_kwargs):
            raise subprocess.TimeoutExpired("simulated-worker", 60)

        driver.subprocess = types.SimpleNamespace(
            run=raise_timeout,
            Popen=real_subprocess.Popen,
            STDOUT=real_subprocess.STDOUT,
            TimeoutExpired=real_subprocess.TimeoutExpired,
        )
        try:
            return driver.run_worker_once(
                args,
                worker="w1",
                phase=phase,
                trial_id=trial_id,
                budget_minutes=1,
                simulate_metric=None,
                simulate_delay_seconds=0,
            )
        finally:
            driver.subprocess = real_subprocess

    def read_results(self) -> list[dict[str, str]]:
        path = self.run_root_base / self.run_tag / "results.tsv"
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    def test_bootstrap_apply_keep_discard_and_collect(self) -> None:
        payload = self.run_driver(
            "bootstrap",
            "--program",
            str(self.program),
            "--target",
            str(self.target),
            "--branch-prefix",
            "autoresearch/",
            "--worker-count",
            "2",
        )
        self.assertEqual(payload["workers"], ["w1", "w2"])

        inspect_payload = self.run_driver("inspect", "--worker", "w1")
        self.assertIn("model.py", inspect_payload["files"])

        overlay = self.root / "overlay"
        overlay.mkdir(parents=True, exist_ok=True)
        (overlay / "model.py").write_text("VALUE = 2\n", encoding="utf-8")
        apply_payload = self.run_driver("apply", "--worker", "w1", "--overlay", str(overlay), "--note", "first patch")
        self.assertIn("model.py", apply_payload["changed_files"])

        baseline_payload = self.run_driver(
            "baseline",
            "--worker",
            "w1",
            "--foreground",
            "--simulate-metric",
            "0.50",
        )
        self.assertEqual(baseline_payload["workers"][0]["result"]["decision"], "keep")

        overlay_w2 = self.root / "overlay-w2"
        overlay_w2.mkdir(parents=True, exist_ok=True)
        (overlay_w2 / "model.py").write_text("VALUE = 3\n", encoding="utf-8")
        self.run_driver("apply", "--worker", "w2", "--overlay", str(overlay_w2))
        discard_payload = self.run_driver(
            "run",
            "--worker",
            "w2",
            "--foreground",
            "--simulate-metric",
            "0.40",
        )
        self.assertEqual(discard_payload["workers"][0]["result"]["decision"], "discard")

        overlay_keep = self.root / "overlay-keep"
        overlay_keep.mkdir(parents=True, exist_ok=True)
        (overlay_keep / "model.py").write_text("VALUE = 4\n", encoding="utf-8")
        self.run_driver("apply", "--worker", "w1", "--overlay", str(overlay_keep))
        keep_payload = self.run_driver(
            "run",
            "--worker",
            "w1",
            "--foreground",
            "--simulate-metric",
            "0.60",
        )
        self.assertEqual(keep_payload["workers"][0]["result"]["decision"], "keep")

        status_payload = self.run_driver("status")
        self.assertAlmostEqual(status_payload["best_metric"], 0.60, places=6)
        best_commit = status_payload["best_commit"]

        sync_payload = self.run_driver("sync-best", "--all-workers")
        self.assertEqual(len(sync_payload["workers"]), 2)
        status_after_sync = self.run_driver("status")
        self.assertEqual(status_after_sync["workers"]["w2"]["last_commit"], best_commit)

        collect_payload = self.run_driver("collect")
        self.assertTrue(Path(collect_payload["state_path"]).exists())
        self.assertTrue(Path(collect_payload["results_path"]).exists())

    def test_foreground_run_executes_command_and_reads_metric_file(self) -> None:
        target_payload = yaml.safe_load(self.target.read_text(encoding="utf-8"))
        target_payload["run"]["environment"]["AR_TEST_SLEEP"] = "0"
        actual_target = self.root / "target-actual.yaml"
        actual_target.write_text(
            yaml.safe_dump(target_payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        self.run_driver(
            "bootstrap",
            "--program",
            str(self.program),
            "--target",
            str(actual_target),
            "--branch-prefix",
            "autoresearch/",
            "--worker-count",
            "1",
        )

        baseline_payload = self.run_driver("baseline", "--worker", "w1", "--foreground")
        result = baseline_payload["workers"][0]["result"]
        self.assertEqual(result["decision"], "keep")
        self.assertAlmostEqual(result["metric"], 0.42, places=6)

        run_dir = Path(result["run_dir"])
        self.assertTrue((run_dir / "results" / "metric.json").exists())
        self.assertTrue((run_dir / "process.log").exists())
        self.assertTrue((run_dir / "command.json").exists())

        status_payload = self.run_driver("status")
        self.assertAlmostEqual(status_payload["best_metric"], 0.42, places=6)

    def test_background_status_stop_and_resume(self) -> None:
        self.run_driver(
            "bootstrap",
            "--program",
            str(self.program),
            "--target",
            str(self.target),
            "--branch-prefix",
            "autoresearch/",
            "--worker-count",
            "2",
        )
        self.run_driver("baseline", "--worker", "w1", "--foreground", "--simulate-metric", "0.50")

        start_payload = self.run_driver(
            "run",
            "--all-workers",
            "--simulate-metric",
            "0.55",
            "--simulate-delay-seconds",
            "2",
        )
        started = [item for item in start_payload["workers"] if item["status"] == "started"]
        self.assertGreaterEqual(len(started), 1)

        time.sleep(0.3)
        status_payload = self.run_driver("status")
        running_count = sum(1 for item in status_payload["workers"].values() if item["status"] == "running")
        self.assertGreaterEqual(running_count, 1)

        stop_payload = self.run_driver("stop", "--all-workers")
        self.assertEqual(len(stop_payload["workers"]), 2)
        time.sleep(0.2)
        status_after_stop = self.run_driver("status")
        stopped_or_finished = {item["status"] for item in status_after_stop["workers"].values()}
        self.assertTrue(stopped_or_finished.issubset({"stopped", "discarded", "kept", "failed", "idle"}))

        resume_payload = self.run_driver(
            "resume",
            "--worker",
            "w1",
            "--foreground",
            "--simulate-metric",
            "0.56",
        )
        self.assertEqual(resume_payload["workers"][0]["status"], "completed")

    def test_timeout_with_metric_uses_normal_keep_and_discard_path(self) -> None:
        self.bootstrap()
        self.run_driver("baseline", "--worker", "w1", "--foreground", "--simulate-metric", "0.50")

        kept = self.run_timeout_trial(trial_id="timeout-keep", phase="run", metric=0.60)
        self.assertEqual(kept["decision"], "keep")
        discarded = self.run_timeout_trial(trial_id="timeout-discard", phase="run", metric=0.40)
        self.assertEqual(discarded["decision"], "discard")

        rows = self.read_results()
        keep_row, discard_row = rows[-2:]
        self.assertEqual(keep_row["completion_reason"], "timeout")
        self.assertEqual(keep_row["metric_extracted"], "True")
        self.assertEqual(keep_row["decision"], "keep")
        self.assertEqual(discard_row["completion_reason"], "timeout")
        self.assertEqual(discard_row["decision"], "discard")

    def test_timeout_without_metric_writes_crash_outcome(self) -> None:
        self.bootstrap()
        self.run_driver("baseline", "--worker", "w1", "--foreground", "--simulate-metric", "0.50")

        with self.assertRaises(Exception):
            self.run_timeout_trial(trial_id="timeout-crash", phase="run", metric=None)

        row = self.read_results()[-1]
        self.assertEqual(row["trial_id"], "timeout-crash")
        self.assertEqual(row["decision"], "crash")
        self.assertEqual(row["completion_reason"], "timeout")
        self.assertEqual(row["metric"], "")
        self.assertEqual(row["metric_extracted"], "False")
        outcome = json.loads(
            (self.run_root_base / self.run_tag / "artifacts" / "w1" / "timeout-crash" / "outcome.json").read_text(
                encoding="utf-8"
            )
        )
        event = json.loads((self.run_root_base / self.run_tag / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        for key in ("worker", "trial_id", "commit", "run_dir", "completion_reason"):
            self.assertEqual(row[key], str(outcome[key]))
            self.assertEqual(event[key], outcome[key])
        state = json.loads((self.run_root_base / self.run_tag / "state.json").read_text(encoding="utf-8"))
        worker = state["workers"]["w1"]
        self.assertEqual(worker["trial_id"], outcome["trial_id"])
        self.assertEqual(worker["trial_commit"], outcome["commit"])
        self.assertEqual(worker["run_dir"], outcome["run_dir"])
        self.assertEqual(worker["completion_reason"], outcome["completion_reason"])

        driver = load_driver_module()
        args = driver.build_parser().parse_args(
            [
                "--run-root-base",
                str(self.run_root_base),
                "--worktree-root-base",
                str(self.worktree_root_base),
                "--lease-root",
                str(self.lease_root),
                "--run-tag",
                self.run_tag,
                "status",
            ]
        )
        result_count = len(self.read_results())
        event_count = len((self.run_root_base / self.run_tag / "events.jsonl").read_text(encoding="utf-8").splitlines())
        driver.record_trial_outcome(args, outcome)
        self.assertEqual(len(self.read_results()), result_count)
        self.assertEqual(
            len((self.run_root_base / self.run_tag / "events.jsonl").read_text(encoding="utf-8").splitlines()),
            event_count,
        )
        conflicting = dict(outcome)
        conflicting["decision"] = "keep"
        with self.assertRaises(driver.AutoresearchV2Error):
            driver.record_trial_outcome(args, conflicting)
        persisted = json.loads(
            (self.run_root_base / self.run_tag / "artifacts" / "w1" / "timeout-crash" / "outcome.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(persisted, outcome)

    def test_process_error_writes_crash_and_resets_worker_to_best(self) -> None:
        target_payload = yaml.safe_load(self.target.read_text(encoding="utf-8"))
        target_payload["run"]["command"] = ["python", "-c", "import sys; sys.exit(7)"]
        bad_target = self.root / "target-process-error.yaml"
        bad_target.write_text(yaml.safe_dump(target_payload, sort_keys=False), encoding="utf-8")
        self.bootstrap(target=bad_target)
        self.run_driver("baseline", "--worker", "w1", "--foreground", "--simulate-metric", "0.50")

        overlay = self.root / "crash-overlay"
        overlay.mkdir()
        (overlay / "model.py").write_text("VALUE = 9\n", encoding="utf-8")
        applied = self.run_driver("apply", "--worker", "w1", "--overlay", str(overlay))
        completed = self.run_driver_process("run", "--worker", "w1", "--foreground")
        self.assertNotEqual(completed.returncode, 0)

        state = json.loads((self.run_root_base / self.run_tag / "state.json").read_text(encoding="utf-8"))
        worker = state["workers"]["w1"]
        head = self._git("-C", worker["worktree"], "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(worker["status"], "failed")
        self.assertIsNone(worker["pid"])
        self.assertEqual(worker["gpu"], "")
        self.assertEqual(worker["trial_commit"], applied["commit"])
        self.assertEqual(head, state["best_commit"])
        row = self.read_results()[-1]
        self.assertEqual(row["decision"], "crash")
        self.assertEqual(row["completion_reason"], "process_error")
        self.assertEqual(row["process_exit_code"], "7")

    def test_failed_trial_releases_gpu_lease(self) -> None:
        target_payload = yaml.safe_load(self.target.read_text(encoding="utf-8"))
        target_payload["run"]["command"] = ["python", "-c", "import sys; sys.exit(7)"]
        leased_target = self.root / "target-leased-process-error.yaml"
        leased_target.write_text(yaml.safe_dump(target_payload, sort_keys=False), encoding="utf-8")
        self.bootstrap(target=leased_target)
        self.run_driver("baseline", "--worker", "w1", "--foreground", "--simulate-metric", "0.50")

        driver = load_driver_module()
        args = driver.build_parser().parse_args(
            [
                "--run-root-base",
                str(self.run_root_base),
                "--worktree-root-base",
                str(self.worktree_root_base),
                "--lease-root",
                str(self.lease_root),
                "--run-tag",
                self.run_tag,
                "worker-runner",
                "--worker",
                "w1",
                "--phase",
                "run",
                "--trial-id",
                "leased-crash",
                "--budget-minutes",
                "1",
            ]
        )
        state_file = self.run_root_base / self.run_tag / "state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["target"]["gpu"] = {"policy": "lease", "selector": "0", "max_wait_seconds": 0}
        state_file.write_text(json.dumps(state), encoding="utf-8")
        released: list[str] = []

        with mock.patch.object(driver, "acquire_gpu_lease", return_value={"gpu": "0"}), mock.patch.object(
            driver, "release_gpu_lease", side_effect=lambda _root, gpu: released.append(gpu)
        ):
            with self.assertRaises(driver.AutoresearchV2Error):
                driver.run_worker_once(
                    args,
                    worker="w1",
                    phase="run",
                    trial_id="leased-crash",
                    budget_minutes=1,
                    simulate_metric=None,
                    simulate_delay_seconds=0,
                )

        self.assertEqual(released, ["0"])
        state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["workers"]["w1"]["gpu"], "")

    def test_metric_parser_error_writes_one_crash_outcome(self) -> None:
        target_payload = yaml.safe_load(self.target.read_text(encoding="utf-8"))
        target_payload["run"]["command"] = ["python", "-c", "pass"]
        missing_metric_target = self.root / "target-missing-metric.yaml"
        missing_metric_target.write_text(yaml.safe_dump(target_payload, sort_keys=False), encoding="utf-8")
        self.bootstrap(target=missing_metric_target)
        self.run_driver("baseline", "--worker", "w1", "--foreground", "--simulate-metric", "0.50")

        completed = self.run_driver_process("run", "--worker", "w1", "--foreground")
        self.assertNotEqual(completed.returncode, 0)
        rows = self.read_results()
        crash_rows = [row for row in rows if row["decision"] == "crash"]
        self.assertEqual(len(crash_rows), 1)
        self.assertEqual(crash_rows[0]["completion_reason"], "metric_error")
        self.assertEqual(crash_rows[0]["process_exit_code"], "0")
        self.assertEqual(crash_rows[0]["metric_extracted"], "False")

    def test_duplicate_baseline_is_rejected_without_changing_best(self) -> None:
        self.bootstrap()
        self.run_driver("baseline", "--worker", "w1", "--foreground", "--simulate-metric", "0.50")
        before = json.loads((self.run_root_base / self.run_tag / "state.json").read_text(encoding="utf-8"))
        best_ref_before = self._git("rev-parse", before["best_branch"]).stdout.strip()
        row_count = len(self.read_results())

        completed = self.run_driver_process(
            "baseline", "--worker", "w1", "--foreground", "--simulate-metric", "0.10"
        )
        self.assertNotEqual(completed.returncode, 0)
        after = json.loads((self.run_root_base / self.run_tag / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(after["baseline"], before["baseline"])
        self.assertEqual(after["best_metric"], before["best_metric"])
        self.assertEqual(after["best_commit"], before["best_commit"])
        self.assertEqual(self._git("rev-parse", after["best_branch"]).stdout.strip(), best_ref_before)
        self.assertEqual(len(self.read_results()), row_count)

    def test_concurrent_baseline_allows_only_one_trial(self) -> None:
        self.bootstrap()
        first = subprocess.Popen(
            self.driver_argv(
                "baseline",
                "--worker",
                "w1",
                "--foreground",
                "--simulate-metric",
                "0.50",
                "--simulate-delay-seconds",
                "1.5",
            ),
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.2)
        second = self.run_driver_process(
            "baseline", "--worker", "w1", "--foreground", "--simulate-metric", "0.60"
        )
        first_stdout, first_stderr = first.communicate(timeout=10)
        self.assertEqual(first.returncode, 0, first_stdout + first_stderr)
        self.assertNotEqual(second.returncode, 0)
        state = json.loads((self.run_root_base / self.run_tag / "state.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(state["baseline"]["metric"], 0.50)
        self.assertEqual(len(self.read_results()), 1)

    def test_doctor_fails_when_git_is_missing(self) -> None:
        env = os.environ.copy()
        env["PATH"] = ""
        completed = subprocess.run(
            [
                sys.executable,
                str(DRIVER),
                "--run-root-base",
                str(self.run_root_base),
                "--worktree-root-base",
                str(self.worktree_root_base),
                "--lease-root",
                str(self.lease_root),
                "--run-tag",
                self.run_tag,
                "doctor",
            ],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        checks = {item["name"]: item for item in payload["checks"]}
        self.assertFalse(checks["git_executable"]["ok"])

    def test_doctor_reports_unwritable_root_and_non_git_target(self) -> None:
        driver = load_driver_module()
        blocked = self.root / "not-a-directory"
        blocked.write_text("blocked\n", encoding="utf-8")
        self.assertFalse(driver.writable_directory_check("blocked", blocked)["ok"])

        blocked_run = subprocess.run(
            [
                "python",
                str(DRIVER),
                "--run-root-base",
                str(blocked),
                "--worktree-root-base",
                str(self.worktree_root_base),
                "--lease-root",
                str(self.lease_root),
                "--run-tag",
                self.run_tag,
                "doctor",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(blocked_run.returncode, 0)
        blocked_payload = json.loads(blocked_run.stdout)
        blocked_checks = {item["name"]: item for item in blocked_payload["checks"]}
        self.assertFalse(blocked_checks["run_root_writable"]["ok"])

        target_payload = yaml.safe_load(self.target.read_text(encoding="utf-8"))
        target_payload["repo"]["remote_root"] = str(self.root / "plain-directory")
        (self.root / "plain-directory").mkdir()
        non_git_target = self.root / "non-git-target.yaml"
        non_git_target.write_text(yaml.safe_dump(target_payload, sort_keys=False), encoding="utf-8")
        completed = self.run_driver_process("doctor", "--target", str(non_git_target))
        self.assertNotEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        checks = {item["name"]: item for item in payload["checks"]}
        self.assertFalse(checks["target_repo"]["ok"])

    def test_old_results_schema_is_rejected(self) -> None:
        driver = load_driver_module()
        path = self.root / "legacy-results.tsv"
        path.write_text("timestamp\tworker\tdecision\n", encoding="utf-8")
        with self.assertRaises(driver.AutoresearchV2Error):
            driver.append_results_row(path, {"timestamp": "now", "worker": "w1", "decision": "crash"})
