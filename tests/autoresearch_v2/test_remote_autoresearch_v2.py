from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import yaml

from support import PROJECT_ROOT

REMOTE_BIN = PROJECT_ROOT / "scripts" / "remote" / "remote-bin"
DRIVER = REMOTE_BIN / "autoresearch_v2_driver.py"


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stdout + completed.stderr)
    return completed.stdout.strip()


def load_driver_module():
    sys.path.insert(0, str(REMOTE_BIN))
    try:
        spec = importlib.util.spec_from_file_location("autoresearch_v2_driver_test", DRIVER)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(REMOTE_BIN))


class CpuFixture:
    def __init__(self, root: Path, direction: str = "higher") -> None:
        self.root = root
        self.repo = root / "repo"
        self.runs = root / "runs"
        self.worktrees = root / "worktrees"
        self.leases = root / "leases"
        self.program = root / "program.md"
        self.target = root / "target.yaml"
        self.run_tag = f"cpu-{direction}"
        self.direction = direction
        self.repo.mkdir(parents=True)
        git(self.repo, "init")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        git(self.repo, "config", "user.name", "CPU Fixture")
        (self.repo / "input.txt").write_text("immutable input\n", encoding="utf-8")
        (self.repo / "score.txt").write_text("10\n", encoding="utf-8")
        (self.repo / "experiment.py").write_text(
            "import json, os\n"
            "from pathlib import Path\n"
            "score=float(Path('score.txt').read_text(encoding='utf-8'))\n"
            "Path('artifact.txt').write_text(f'artifact={score}\\n', encoding='utf-8')\n"
            "root=Path(os.environ['AR2_RESULTS_DIR'])\n"
            "root.mkdir(parents=True, exist_ok=True)\n"
            "tmp=root/'metrics.json.tmp'\n"
            "tmp.write_text(json.dumps({'primary_metric': score, 'metrics': {'secondary': -score}}), encoding='utf-8')\n"
            "os.replace(tmp, root/'metrics.json')\n",
            encoding="utf-8",
        )
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "fixture")
        self.program.write_text(
            "---\n"
            "goal: Exercise a generic CPU target.\n"
            "metric: primary_metric\n"
            f"direction: {direction}\n"
            "budget_mode: default\n"
            "worker_count: 1\n"
            "keep_threshold: 0.0\n"
            "mutable_paths:\n  - score.txt\n"
            "---\n\n# CPU fixture\n",
            encoding="utf-8",
        )
        self.target.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "name": "cpu-fixture",
                    "repo": {
                        "path": str(self.repo),
                        "base_ref": "HEAD",
                        "mutable_paths": ["score.txt"],
                    },
                    "run": {
                        "cwd": ".",
                        "argv": [sys.executable, "experiment.py"],
                        "env": {"FIXTURE_MODE": "cpu"},
                        "budget_minutes": 1,
                    },
                    "metric": {
                        "path": "metrics.json",
                        "primary_key": "primary_metric",
                        "direction": direction,
                    },
                    "artifacts": ["artifact.txt"],
                    "provenance": {"inputs": ["input.txt"]},
                    "gpu": {"mode": "none"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def invoke(self, command: str, *arguments: str, expected: int = 0) -> dict:
        completed = subprocess.run(
            [
                sys.executable,
                str(DRIVER),
                "--run-root-base",
                str(self.runs),
                "--worktree-root-base",
                str(self.worktrees),
                "--lease-root",
                str(self.leases),
                "--run-tag",
                self.run_tag,
                command,
                *arguments,
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != expected:
            raise AssertionError(f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
        return json.loads(completed.stdout)

    def bootstrap(self) -> None:
        self.invoke("doctor", "--target", str(self.target))
        self.invoke(
            "bootstrap",
            "--program",
            str(self.program),
            "--target",
            str(self.target),
            "--branch-prefix",
            "fixture/",
            "--worker-count",
            "1",
        )

    def apply_score(self, score: float) -> None:
        overlay = self.root / "overlay" / "score.txt"
        overlay.parent.mkdir(exist_ok=True)
        overlay.write_text(f"{score}\n", encoding="utf-8")
        self.invoke("apply", "--worker", "w1", "--overlay", str(overlay))


class RemoteAutoresearchV2Test(unittest.TestCase):
    def test_cpu_baseline_keep_discard_collect_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CpuFixture(Path(temporary), "higher")
            fixture.bootstrap()
            baseline = fixture.invoke("baseline", "--worker", "w1", "--foreground")
            self.assertEqual(baseline["workers"][0]["result"]["metric"], 10.0)

            fixture.apply_score(12.5)
            kept = fixture.invoke("run", "--worker", "w1", "--foreground")
            self.assertEqual(kept["workers"][0]["result"]["decision"], "keep")

            fixture.apply_score(-3)
            discarded = fixture.invoke("run", "--worker", "w1", "--foreground")
            result = discarded["workers"][0]["result"]
            self.assertEqual(result["decision"], "discard")
            self.assertEqual(result["metric"], -3.0)
            worker_score = fixture.worktrees / fixture.run_tag / "w1" / "score.txt"
            self.assertEqual(float(worker_score.read_text(encoding="utf-8")), 12.5)

            collected = fixture.invoke("collect")
            self.assertEqual(collected["command"], "collect")
            trial = fixture.runs / fixture.run_tag / "artifacts" / "w1" / "iter-0003"
            provenance = json.loads((trial / "provenance.json").read_text(encoding="utf-8"))
            execution = json.loads((trial / "execution.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["resource"]["mode"], "none")
            self.assertNotIn("AR2_GPU_ID", provenance["environment"]["runtime_keys"])
            self.assertEqual(len(provenance["inputs"]), 1)
            self.assertEqual(execution["artifacts"][0]["path"], "artifact.txt")
            self.assertTrue((trial / execution["artifacts"][0]["archive_path"]).is_file())
            events = (fixture.runs / fixture.run_tag / "events.jsonl").read_text(encoding="utf-8")
            for event in ("run_started", "metric_recorded", "artifact_recorded", "run_finished"):
                self.assertIn(f'"event": "{event}"', events)
            self.assertFalse(any(fixture.leases.glob("*.json")))

    def test_lower_direction_keeps_negative_metric(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CpuFixture(Path(temporary), "lower")
            fixture.bootstrap()
            fixture.invoke("baseline", "--worker", "w1", "--foreground")
            fixture.apply_score(-5)
            result = fixture.invoke("run", "--worker", "w1", "--foreground")
            self.assertEqual(result["workers"][0]["result"]["decision"], "keep")
            self.assertEqual(result["workers"][0]["result"]["metric"], -5.0)

    def test_metrics_file_validation(self) -> None:
        module = load_driver_module()
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            results = run_dir / "results"
            results.mkdir()
            state = {"target": {"metric": {"path": "metrics.json"}}}
            path = results / "metrics.json"
            invalid = [
                {},
                {"primary_metric": True},
                {"primary_metric": float("inf")},
                {"primary_metric": 1, "metrics": []},
                {"primary_metric": 1, "metrics": {"bad": float("nan")}},
            ]
            for payload in invalid:
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(module.AutoresearchV2Error):
                        module.measure_metric(state, run_dir, None)

    def test_timeout_terminates_process_tree(self) -> None:
        module = load_driver_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child_pid_path = root / "child.pid"
            code = (
                "import pathlib, subprocess, sys, time; "
                "p=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
                f"pathlib.Path({str(child_pid_path)!r}).write_text(str(p.pid)); "
                "time.sleep(60)"
            )
            return_code, timed_out = module.run_process_tree(
                [sys.executable, "-c", code], root, os.environ.copy(), root / "process.log", 1
            )
            self.assertIsNone(return_code)
            self.assertTrue(timed_out)
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            time.sleep(0.2)
            with self.assertRaises(OSError):
                os.kill(child_pid, 0)

    def test_doctor_rejects_old_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = CpuFixture(root)
            legacy = root / "legacy.yaml"
            legacy.write_text("name: legacy\n", encoding="utf-8")
            payload = fixture.invoke("doctor", "--target", str(legacy), expected=1)
            self.assertIn("unsupported-schema", payload["error"])


if __name__ == "__main__":
    unittest.main()
