from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DRIVER = PROJECT_ROOT / "scripts" / "remote" / "remote-bin" / "autoresearch_v2_driver.py"


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
        completed = subprocess.run(
            [
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
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if expect_ok and completed.returncode != 0:
            raise AssertionError(f"driver failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
        payload = json.loads(completed.stdout)
        if expect_ok:
            self.assertTrue(payload["ok"], payload)
        return payload

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
