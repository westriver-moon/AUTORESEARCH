from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROJECT_ROOT / ".agents" / "skills" / "codex-autoresearch"


class CodexAutoresearchProjectAdapterTest(unittest.TestCase):
    def run_cmd(
        self,
        args: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
        self.assertEqual(
            completed.returncode,
            0,
            f"command failed: {args}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        return completed

    def git(self, repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
        completed = self.run_cmd(["git", *args], cwd=repo, env=env)
        return completed.stdout.strip()

    def test_project_local_skill_is_explicit_foreground_only(self) -> None:
        skill_md = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        manifest = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertTrue((SKILL_ROOT / "SKILL.md").exists())
        self.assertIn("name: codex-autoresearch", skill_md)
        self.assertIn("Invoke only when the user explicitly writes `$codex-autoresearch`.", skill_md)
        self.assertRegex(manifest, r"(?m)^\s*allow_implicit_invocation:\s*false\s*$")
        self.assertIn("Use foreground mode only", skill_md)
        self.assertIn("Do not use `exec` mode or `codex exec`.", skill_md)
        self.assertIn("Never run", skill_md)
        self.assertIn("autoresearch_hooks_ctl.py install", skill_md)
        self.assertIn("not `python3`", skill_md)

    def test_foreground_metric_simulation_keeps_improvement_and_rolls_back_regression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            repo = tmp_root / "repo"
            fakebin = tmp_root / "fakebin"
            marker = fakebin / "codex-called.txt"
            repo.mkdir()
            fakebin.mkdir()

            if os.name == "nt":
                (fakebin / "codex.cmd").write_text(
                    "@echo off\r\necho called > \"%~dp0codex-called.txt\"\r\nexit /b 99\r\n",
                    encoding="ascii",
                )
            else:
                codex = fakebin / "codex"
                codex.write_text(
                    "#!/bin/sh\necho called > \"$(dirname \"$0\")/codex-called.txt\"\nexit 99\n",
                    encoding="ascii",
                )
                codex.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")

            self.git(repo, "init", env=env)
            self.git(repo, "config", "user.email", "adapter-test@example.invalid", env=env)
            self.git(repo, "config", "user.name", "Adapter Test", env=env)

            (repo / "score.txt").write_text("1\n", encoding="utf-8")
            (repo / "read_metric.py").write_text(
                "from pathlib import Path\nprint(Path('score.txt').read_text().strip())\n",
                encoding="utf-8",
            )
            self.git(repo, "add", "score.txt", "read_metric.py", env=env)
            self.git(repo, "commit", "-m", "baseline", env=env)
            baseline_commit = self.git(repo, "rev-parse", "--short", "HEAD", env=env)

            init_script = SKILL_ROOT / "scripts" / "autoresearch_init_run.py"
            record_script = SKILL_ROOT / "scripts" / "autoresearch_record_iteration.py"

            self.run_cmd(
                [
                    sys.executable,
                    str(init_script),
                    "--repo",
                    str(repo),
                    "--workspace-root",
                    str(repo),
                    "--mode",
                    "loop",
                    "--session-mode",
                    "foreground",
                    "--goal",
                    "Improve score",
                    "--scope",
                    "score.txt",
                    "--metric-name",
                    "score",
                    "--direction",
                    "higher",
                    "--verify",
                    "python read_metric.py",
                    "--baseline-metric",
                    "1",
                    "--baseline-commit",
                    baseline_commit,
                    "--baseline-description",
                    "initial score",
                ],
                cwd=repo,
                env=env,
            )

            artifact_root = repo / "autoresearch-results"
            results_path = artifact_root / "results.tsv"
            state_path = artifact_root / "state.json"
            context_path = artifact_root / "context.json"
            self.assertTrue(results_path.exists())
            self.assertTrue(state_path.exists())
            self.assertTrue(context_path.exists())

            (repo / "score.txt").write_text("2\n", encoding="utf-8")
            self.git(repo, "add", "score.txt", env=env)
            self.git(repo, "commit", "-m", "experiment: improve score", env=env)
            good_commit = self.git(repo, "rev-parse", "--short", "HEAD", env=env)

            self.run_cmd(
                [
                    sys.executable,
                    str(record_script),
                    "--status",
                    "keep",
                    "--metric",
                    "2",
                    "--commit",
                    good_commit,
                    "--guard",
                    "pass",
                    "--description",
                    "improved score",
                ],
                cwd=repo,
                env=env,
            )

            (repo / "score.txt").write_text("0\n", encoding="utf-8")
            self.git(repo, "add", "score.txt", env=env)
            self.git(repo, "commit", "-m", "experiment: regress score", env=env)
            bad_commit = self.git(repo, "rev-parse", "--short", "HEAD", env=env)

            self.run_cmd(
                [
                    sys.executable,
                    str(record_script),
                    "--status",
                    "discard",
                    "--metric",
                    "0",
                    "--commit",
                    bad_commit,
                    "--guard",
                    "pass",
                    "--description",
                    "regressed score",
                ],
                cwd=repo,
                env=env,
            )

            self.git(repo, "reset", "--hard", good_commit, env=env)

            self.assertEqual((repo / "score.txt").read_text(encoding="utf-8"), "2\n")

            results_text = results_path.read_text(encoding="utf-8")
            self.assertIn("\tbaseline\tinitial score", results_text)
            self.assertIn("\tkeep\timproved score", results_text)
            self.assertIn("\tdiscard\tregressed score", results_text)

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["config"]["session_mode"], "foreground")
            self.assertEqual(state["state"]["best_metric"], 2)
            self.assertEqual(state["state"]["current_metric"], 2)
            self.assertEqual(state["state"]["last_trial_metric"], 0)
            self.assertEqual(state["state"]["last_status"], "discard")
            self.assertEqual(state["state"]["keeps"], 1)
            self.assertEqual(state["state"]["discards"], 1)

            context = json.loads(context_path.read_text(encoding="utf-8"))
            self.assertEqual(context["session_mode"], "foreground")
            self.assertIsNone(context["launch_path"])
            self.assertIsNone(context["runtime_path"])
            self.assertIsNone(context["log_path"])

            self.assertFalse((artifact_root / "launch.json").exists())
            self.assertFalse((artifact_root / "runtime.json").exists())
            self.assertFalse((artifact_root / "runtime.log").exists())
            self.assertFalse(marker.exists(), "Codex CLI/background marker should not be called")


if __name__ == "__main__":
    unittest.main()
