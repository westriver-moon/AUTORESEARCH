from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RemoteAutoresearchV2WrapperTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._copy_fixture_files()

        self.program_path = self.workspace / "autoresearch" / "program.md"
        self.target_path = self.workspace / "autoresearch" / "targets" / "unit-target.yaml"
        self.program_path.parent.mkdir(parents=True, exist_ok=True)
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        self.program_path.write_text(
            textwrap.dedent(
                """
                ---
                goal: Wrapper smoke
                metric: primary_metric
                direction: higher
                budget_mode: short
                worker_count: 1
                keep_threshold: 0.0
                mutable_paths:
                  - TVI-LFM/main.py
                ---

                # Wrapper Smoke
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self.target_path.write_text(
            textwrap.dedent(
                """
                name: wrapper-smoke
                repo:
                  remote_root: /tmp/repo
                  base_ref: main
                  mutable_paths:
                    - TVI-LFM/main.py
                run:
                  cwd: TVI-LFM
                  command:
                    - "{python_bin}"
                    - "-c"
                    - "print('ok')"
                  budget_minutes:
                    short: 1
                    medium: 1
                    long: 1
                  metric:
                    parser: json_file
                    path: metrics.json
                    primary_key: primary_metric
                    direction: higher
                artifacts:
                  collect:
                    - metrics.json
                training:
                  python_bin: /usr/bin/python3
                gpu:
                  policy: none
                  selector: "0"
                  max_wait_seconds: 0
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        config_dir = self.workspace / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        self.remote_root = "/tmp/ar2"
        (config_dir / "autoresearch-v2.example.psd1").write_text(
            textwrap.dedent(
                f"""
                @{{
                    ProgramPath = 'autoresearch/program.md'
                    TargetPath = 'autoresearch/targets/unit-target.yaml'
                    LocalRunRoot = 'autoresearch-runs'
                    BranchPrefix = 'autoresearch/'
                    DefaultWorkerCount = 1
                    DefaultBudgetMinutes = 30
                    DefaultKeepThreshold = '0.0'
                    DefaultLeaseWaitSeconds = 300

                    RemoteControllerRoot = '{self.remote_root}'
                    RemoteRunRoot = '{self.remote_root}/runs'
                    RemoteWorktreeRoot = '{self.remote_root}/worktrees'
                    RemoteLeaseRoot = '{self.remote_root}/leases'
                    RemoteBridgeEntry = '{self.remote_root}/bin/run_autoresearch_v2_bridge.sh'
                }}
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (config_dir / "remote.local.psd1").write_text(
            textwrap.dedent(
                """
                @{
                    RemoteHost = 'fake-remote'
                    TunnelAlias = 'fake-tunnel'
                    SshConfigPath = ''
                    LocalTunnelScript = ''
                    ProxyTaskName = 'Fake'
                    RemoteProxyRoot = '/tmp/proxy'
                    RemoteWorkspaceRoot = '/tmp/workspace'
                    ConnectTimeoutSec = 15
                    ProxyPort = 7897
                }
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self.ssh_config = self.workspace / "fake_ssh_config"
        self.ssh_config.write_text("Host fake-remote\n", encoding="utf-8")

        self.ssh_log = self.workspace / "fake_ssh.jsonl"
        self.scp_log = self.workspace / "fake_scp.jsonl"
        self.run_tag = "wrapper-run"
        self.bridge_exit_code = 0
        self._write_fake_transport()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _copy_fixture_files(self) -> None:
        for relative in (
            Path("scripts/remote/autoresearch-v2.ps1"),
            Path("scripts/remote/lib/common.ps1"),
            Path("scripts/remote/lib/ssh.ps1"),
            Path("scripts/remote/lib/result.ps1"),
            Path("scripts/remote/lib/autoresearch_v2.ps1"),
            Path(".agents/skills/codex-autoresearch-v2/scripts/autoresearch_v2_contracts.py"),
            Path(".agents/skills/codex-autoresearch-v2/scripts/autoresearch_program_validate.py"),
            Path(".agents/skills/codex-autoresearch-v2/scripts/autoresearch_target_validate.py"),
        ):
            destination = self.workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT_ROOT / relative, destination)

    def _write_fake_transport(self) -> None:
        fake_ssh_py = self.workspace / "fake_ssh.py"
        fake_scp_py = self.workspace / "fake_scp.py"
        fake_ssh_cmd = self.workspace / "fake_ssh.cmd"
        fake_scp_cmd = self.workspace / "fake_scp.cmd"

        fake_ssh_py.write_text(
            textwrap.dedent(
                """
                from __future__ import annotations

                import json
                import os
                import sys
                from pathlib import Path

                log_path = Path(os.environ["AR2_FAKE_SSH_LOG"])
                run_tag = os.environ["AR2_FAKE_RUN_TAG"]
                remote_root = os.environ["AR2_FAKE_REMOTE_ROOT"]
                command = sys.argv[-1] if len(sys.argv) > 1 else ""
                entry = {"argv": sys.argv[1:], "remote_command": command}
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\\n")

                if "run_autoresearch_v2_bridge.sh" not in command:
                    raise SystemExit(0)

                payload: dict[str, object]
                if " bootstrap" in command or "'bootstrap'" in command:
                    payload = {
                        "ok": True,
                        "workers": ["w1"],
                        "run_root": f"{remote_root}/runs/{run_tag}",
                    }
                elif " inspect" in command or "'inspect'" in command:
                    payload = {
                        "ok": True,
                        "export_root": f"{remote_root}/runs/{run_tag}/exports/w1/inspect",
                        "files": ["TVI-LFM/main.py"],
                    }
                elif " doctor" in command or "'doctor'" in command:
                    payload = {"ok": True, "command": "doctor"}
                else:
                    payload = {"ok": True}
                forced_output = os.environ.get("AR2_FAKE_BRIDGE_OUTPUT")
                print(forced_output if forced_output is not None else json.dumps(payload, ensure_ascii=False))
                raise SystemExit(int(os.environ.get("AR2_FAKE_BRIDGE_EXIT", "0")))
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        fake_scp_py.write_text(
            textwrap.dedent(
                """
                from __future__ import annotations

                import json
                import os
                import sys
                from pathlib import Path

                log_path = Path(os.environ["AR2_FAKE_SCP_LOG"])
                args = sys.argv[1:]
                positional: list[str] = []
                i = 0
                while i < len(args):
                    current = args[i]
                    if current == "-F":
                        i += 2
                        continue
                    if current == "-r":
                        i += 1
                        continue
                    positional.append(current)
                    i += 1

                if len(positional) != 2:
                    print(f"unexpected scp args: {args}", file=sys.stderr)
                    raise SystemExit(2)

                first, second = positional
                entry = {"argv": args, "first": first, "second": second}
                if first.startswith("fake-remote:"):
                    destination = Path(second)
                    if not destination.parent.exists():
                        print(f"mkdir {destination.as_posix()}: No such file or directory", file=sys.stderr)
                        raise SystemExit(2)
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / "downloaded.txt").write_text("ok\\n", encoding="utf-8")
                    entry["direction"] = "download"
                else:
                    entry["direction"] = "upload"

                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\\n")
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        fake_ssh_cmd.write_text(
            f'@echo off\r\n"{sys.executable}" "{fake_ssh_py}" %*\r\n',
            encoding="utf-8",
        )
        fake_scp_cmd.write_text(
            f'@echo off\r\n"{sys.executable}" "{fake_scp_py}" %*\r\n',
            encoding="utf-8",
        )

        self.fake_ssh_cmd = fake_ssh_cmd
        self.fake_scp_cmd = fake_scp_cmd

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["CODEX_TEST_SSH_EXE"] = str(self.fake_ssh_cmd)
        env["CODEX_TEST_SCP_EXE"] = str(self.fake_scp_cmd)
        env["AR2_FAKE_SSH_LOG"] = str(self.ssh_log)
        env["AR2_FAKE_SCP_LOG"] = str(self.scp_log)
        env["AR2_FAKE_RUN_TAG"] = self.run_tag
        env["AR2_FAKE_REMOTE_ROOT"] = self.remote_root
        env["AR2_FAKE_BRIDGE_EXIT"] = str(self.bridge_exit_code)
        return env

    def _read_jsonl(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def run_ps(self, *extra_args: str, expect_ok: bool = True) -> dict[str, object]:
        completed = self.run_ps_process(*extra_args)
        if expect_ok and completed.returncode != 0:
            raise AssertionError(f"powershell wrapper failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
        payload = json.loads(completed.stdout)
        if expect_ok:
            self.assertTrue(payload["ok"], payload)
        return payload

    def run_ps_process(self, *extra_args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.workspace / "scripts" / "remote" / "autoresearch-v2.ps1"),
                *extra_args,
                "-RemoteHost",
                "fake-remote",
                "-SshConfigPath",
                str(self.ssh_config),
                "-Json",
            ],
            cwd=self.workspace,
            env=self._env(),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_deploy_uses_posix_remote_parent(self) -> None:
        payload = self.run_ps("-Mode", "deploy", "-RunTag", self.run_tag)
        self.assertTrue(payload["ok"])

        ssh_entries = self._read_jsonl(self.ssh_log)
        scp_entries = self._read_jsonl(self.scp_log)
        self.assertTrue(any("/tmp/ar2/bin" in str(entry["remote_command"]) for entry in ssh_entries))
        uploaded_targets = [str(entry["second"]) for entry in scp_entries if entry["direction"] == "upload"]
        self.assertTrue(any(target.endswith("/tmp/ar2/bin/run_autoresearch_v2_bridge.sh") for target in uploaded_targets))
        self.assertTrue(all("\\" not in target for target in uploaded_targets))

    def test_bootstrap_uses_staging_spec_uploads(self) -> None:
        payload = self.run_ps("-Mode", "bootstrap", "-RunTag", self.run_tag, "-WorkerCount", "1")
        self.assertEqual(payload["details"]["remote"]["workers"], ["w1"])

        ssh_entries = self._read_jsonl(self.ssh_log)
        scp_entries = self._read_jsonl(self.scp_log)
        uploaded_targets = [str(entry["second"]) for entry in scp_entries if entry["direction"] == "upload"]
        self.assertTrue(any(target.endswith(f"/tmp/ar2/uploads/{self.run_tag}/spec/program.md") for target in uploaded_targets))
        self.assertTrue(any(target.endswith(f"/tmp/ar2/uploads/{self.run_tag}/spec/target.yaml") for target in uploaded_targets))
        self.assertFalse(any(f"/tmp/ar2/runs/{self.run_tag}/spec" in str(entry["remote_command"]) for entry in ssh_entries))

    def test_inspect_creates_local_parent_before_download(self) -> None:
        payload = self.run_ps("-Mode", "inspect", "-RunTag", self.run_tag, "-Worker", "w1")
        self.assertTrue(payload["ok"])

        local_inspect = self.workspace / "autoresearch-runs" / self.run_tag / "inspect" / "w1"
        self.assertTrue((local_inspect / "downloaded.txt").exists())
        scp_entries = self._read_jsonl(self.scp_log)
        downloads = [entry for entry in scp_entries if entry["direction"] == "download"]
        self.assertEqual(len(downloads), 1)

    def test_nonzero_bridge_exit_is_propagated_for_allow_failure_modes(self) -> None:
        self.bridge_exit_code = 7
        for mode in ("baseline", "run", "resume", "status", "collect", "stop", "sync-best"):
            with self.subTest(mode=mode):
                completed = self.run_ps_process("-Mode", mode, "-RunTag", self.run_tag, "-Foreground")
                self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                payload = json.loads(completed.stdout)
                self.assertFalse(payload["ok"])
                status_path = self.workspace / "autoresearch-runs" / self.run_tag / "remote" / f"{mode}.json"
                self.assertTrue(status_path.exists())
                self.assertFalse(json.loads(status_path.read_text(encoding="utf-8-sig"))["ok"])

    def test_doctor_propagates_nonzero_bridge_exit(self) -> None:
        self.bridge_exit_code = 7
        completed = self.run_ps_process("-Mode", "doctor", "-RunTag", self.run_tag)
        self.assertNotEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])

    def test_non_json_bridge_failure_preserves_raw_diagnostics(self) -> None:
        self.bridge_exit_code = 7
        env = self._env()
        env["AR2_FAKE_BRIDGE_OUTPUT"] = "bridge exploded before emitting JSON"
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.workspace / "scripts" / "remote" / "autoresearch-v2.ps1"),
                "-Mode",
                "status",
                "-RunTag",
                self.run_tag,
                "-RemoteHost",
                "fake-remote",
                "-SshConfigPath",
                str(self.ssh_config),
                "-Json",
            ],
            cwd=self.workspace,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["details"]["raw"], "bridge exploded before emitting JSON")
        self.assertTrue(payload["details"]["error"])


if __name__ == "__main__":
    unittest.main()
