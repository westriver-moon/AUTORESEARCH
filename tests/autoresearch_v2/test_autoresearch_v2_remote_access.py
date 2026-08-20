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

from support import PROJECT_ROOT

POWERSHELL = shutil.which("pwsh") or shutil.which("powershell.exe") or "powershell.exe"

class AutoresearchV2RemoteAccessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        for relative in (
            "scripts/remote/autoresearch-v2.ps1",
            "scripts/remote/lib/common.ps1",
            "scripts/remote/lib/config.ps1",
            "scripts/remote/lib/profile_session_state.ps1",
            "scripts/remote/lib/remote_access.ps1",
            "scripts/remote/lib/autoresearch_v2.ps1",
        ):
            destination = self.workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT_ROOT / relative, destination)

        config_dir = self.workspace / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "autoresearch-v2.example.psd1").write_text(
            textwrap.dedent(
                """
                @{
                    RemoteHost = 'example-host'
                    SshConfigPath = ''
                    ConnectTimeoutSec = 5
                    ProxyMode = 'disabled'
                    ActiveRemoteProfile = 'fake-profile'
                    RemoteProfiles = @{
                        'fake-profile' = @{
                            RemoteHost = 'fake-remote'
                            SelectionOrder = 1
                            ExpectedHostname = 'fake-host'
                            ExpectedUser = 'fake-user'
                            RemoteControllerRoot = '/srv/fake-profile/autoresearch-v2'
                            RemoteRunRoot = '/srv/fake-profile/autoresearch-v2/runs'
                            RemoteWorktreeRoot = '/srv/fake-profile/autoresearch-v2/worktrees'
                            RemoteLeaseRoot = '/srv/fake-profile/autoresearch-v2/leases'
                            RemoteBridgeEntry = '/srv/fake-profile/autoresearch-v2/run_autoresearch_v2_bridge.sh'
                        }
                        'fake-alt' = @{
                            RemoteHost = 'fake-alt'
                            SelectionOrder = 2
                            ExpectedHostname = 'fake-alt-host'
                            ExpectedUser = 'fake-alt-user'
                            RemoteControllerRoot = '/srv/fake-alt/autoresearch-v2'
                            RemoteRunRoot = '/srv/fake-alt/autoresearch-v2/runs'
                            RemoteWorktreeRoot = '/srv/fake-alt/autoresearch-v2/worktrees'
                            RemoteLeaseRoot = '/srv/fake-alt/autoresearch-v2/leases'
                            RemoteBridgeEntry = '/srv/fake-alt/autoresearch-v2/run_autoresearch_v2_bridge.sh'
                        }
                    }
                    LocalRunRoot = 'autoresearch-runs'
                    RemoteControllerRoot = '/tmp/autoresearch-v2'
                    RemoteRunRoot = '/tmp/autoresearch-v2/runs'
                    RemoteWorktreeRoot = '/tmp/autoresearch-v2/worktrees'
                    RemoteLeaseRoot = '/tmp/autoresearch-v2/leases'
                    RemoteBridgeEntry = '/tmp/autoresearch-v2/run_autoresearch_v2_bridge.sh'
                }
                """
            ).strip()
            + "\n",
            encoding="ascii",
        )
        self.ssh_config = self.workspace / "ssh_config"
        self.ssh_config.write_text("Host fake-remote\n", encoding="ascii")
        self.ssh_log = self.workspace / "ssh-log.json"
        self.session_state_root = self.workspace / "session-state"
        self.thread_id = "test-thread"
        fake_script = self.workspace / "fake_ssh.py"
        fake_script.write_text(
            textwrap.dedent(
                """
                import json
                import os
                import sys
                from pathlib import Path

                Path(os.environ['AR2_TEST_SSH_LOG']).write_text(
                    json.dumps(sys.argv[1:]), encoding='utf-8'
                )
                if os.environ.get('AR2_TEST_SSH_OUTPUT'):
                    print(os.environ['AR2_TEST_SSH_OUTPUT'])
                """
            ).strip()
            + "\n",
            encoding="ascii",
        )
        self.fake_ssh = self.workspace / "fake_ssh.cmd"
        self.fake_ssh.write_text(
            f'@echo off\r\n"{sys.executable}" "{fake_script}" %*\r\n',
            encoding="ascii",
        )
        self.scp_log = self.workspace / "scp-log.json"
        fake_scp_script = self.workspace / "fake_scp.py"
        fake_scp_script.write_text(
            textwrap.dedent(
                """
                import json
                import os
                import sys
                from pathlib import Path

                Path(os.environ['AR2_TEST_SCP_LOG']).write_text(
                    json.dumps(sys.argv[1:]), encoding='utf-8'
                )
                """
            ).strip()
            + "\n",
            encoding="ascii",
        )
        self.fake_scp = self.workspace / "fake_scp.cmd"
        self.fake_scp.write_text(
            f'@echo off\r\n"{sys.executable}" "{fake_scp_script}" %*\r\n',
            encoding="ascii",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_access_doctor_resolves_profile_and_owns_ssh_arguments(self) -> None:
        environment = os.environ.copy()
        environment["CODEX_TEST_SSH_EXE"] = str(self.fake_ssh)
        environment["AR2_TEST_SSH_LOG"] = str(self.ssh_log)
        environment["AR2_TEST_SSH_OUTPUT"] = "fake-host\nfake-user"
        completed = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.workspace / "scripts" / "remote" / "autoresearch-v2.ps1"),
                "-Mode",
                "access-doctor",
                "-RemoteProfile",
                "fake-profile",
                "-SshConfigPath",
                str(self.ssh_config),
                "-Json",
            ],
            cwd=self.workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"], result)
        details = result["details"]["remote_access"]
        self.assertEqual(details["profile"], "fake-profile")
        self.assertEqual(details["remote_host"], "fake-remote")
        self.assertEqual(details["proxy_mode"], "disabled")

        arguments = json.loads(self.ssh_log.read_text(encoding="utf-8"))
        self.assertIn("-F", arguments)
        self.assertIn(str(self.ssh_config), arguments)
        self.assertIn("BatchMode=yes", arguments)
        self.assertIn("ConnectTimeout=5", arguments)
        self.assertIn("fake-remote", arguments)
        self.assertEqual(arguments[-1], "hostname; whoami")
        self.assertTrue(details["identity_ok"])

    def run_selector(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
    ) -> dict[str, object]:
        env = os.environ.copy()
        env["CODEX_THREAD_ID"] = self.thread_id
        env["CODEX_AUTORESEARCH_STATE_ROOT"] = str(self.session_state_root)
        if environment:
            env.update(environment)
        completed = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PROJECT_ROOT / "scripts" / "remote" / "select-profile.ps1"),
                "-ProjectRoot",
                str(self.workspace),
                "-NonInteractive",
                *arguments,
            ],
            cwd=self.workspace,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def test_selector_resolves_active_profile_without_interaction(self) -> None:
        result = self.run_selector()
        self.assertEqual(result["remote_profile"], "fake-profile")
        self.assertEqual(result["remote_host"], "fake-remote")
        self.assertFalse(result["locked"])

    def test_selector_validates_explicit_profile_without_interaction(self) -> None:
        result = self.run_selector("-RemoteProfile", "fake-alt")
        self.assertEqual(result["remote_profile"], "fake-alt")
        self.assertEqual(result["remote_host"], "fake-alt")

    def test_session_lock_reused_until_force_switch(self) -> None:
        first = self.run_selector()
        self.assertFalse(first["locked"])

        reused = self.run_selector()
        self.assertTrue(reused["locked"])
        self.assertEqual(reused["remote_profile"], "fake-profile")

        switched = self.run_selector("-RemoteProfile", "fake-alt", "-Force")
        self.assertFalse(switched["locked"])
        self.assertEqual(switched["remote_profile"], "fake-alt")

        reused_after_switch = self.run_selector()
        self.assertTrue(reused_after_switch["locked"])
        self.assertEqual(reused_after_switch["remote_profile"], "fake-alt")

    def test_access_doctor_fails_on_remote_identity_mismatch(self) -> None:
        environment = os.environ.copy()
        environment["CODEX_TEST_SSH_EXE"] = str(self.fake_ssh)
        environment["AR2_TEST_SSH_LOG"] = str(self.ssh_log)
        environment["AR2_TEST_SSH_OUTPUT"] = "wrong-host\nwrong-user"
        completed = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.workspace / "scripts" / "remote" / "autoresearch-v2.ps1"),
                "-Mode",
                "access-doctor",
                "-RemoteProfile",
                "fake-profile",
                "-SshConfigPath",
                str(self.ssh_config),
                "-Json",
            ],
            cwd=self.workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertFalse(result["ok"])
        self.assertEqual(result["details"]["remote_access"]["remote_hostname"], "wrong-host")

    def test_scp_directions_share_transport_arguments(self) -> None:
        environment = os.environ.copy()
        environment["CODEX_TEST_SCP_EXE"] = str(self.fake_scp)
        environment["AR2_TEST_SCP_LOG"] = str(self.scp_log)
        common = self.workspace / "scripts" / "remote" / "lib" / "common.ps1"
        access = self.workspace / "scripts" / "remote" / "lib" / "remote_access.ps1"
        access_literal = (
            "@{RemoteHost='fake-remote'; SshConfigPath='ssh-config'; ConnectTimeoutSec=7}"
        )

        commands = (
            (
                f". '{common}'; . '{access}'; "
                f"Copy-AutoresearchToRemote -Access {access_literal} -LocalPath 'source.txt' "
                "-RemotePath '/tmp/input' -Recurse | Out-Null",
                ["-F", "ssh-config", "-o", "BatchMode=yes", "-o", "ConnectTimeout=7", "-r", "source.txt", "fake-remote:/tmp/input"],
            ),
            (
                f". '{common}'; . '{access}'; "
                f"Copy-AutoresearchFromRemote -Access {access_literal} -RemotePath '/tmp/output' "
                "-LocalPath 'result.txt' | Out-Null",
                ["-F", "ssh-config", "-o", "BatchMode=yes", "-o", "ConnectTimeout=7", "fake-remote:/tmp/output", "result.txt"],
            ),
        )
        for command, expected in commands:
            completed = subprocess.run(
                [POWERSHELL, "-NoProfile", "-Command", command],
                cwd=self.workspace,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertEqual(json.loads(self.scp_log.read_text(encoding="utf-8")), expected)

    def test_runtime_roots_follow_selected_remote_profile(self) -> None:
        config_lib = self.workspace / "scripts" / "remote" / "lib" / "config.ps1"
        runtime_lib = self.workspace / "scripts" / "remote" / "lib" / "autoresearch_v2.ps1"
        command = (
            f". '{config_lib}'; . '{runtime_lib}'; "
            f"Get-AutoresearchV2Config -ProjectRoot '{self.workspace}' "
            "-RemoteProfile 'fake-profile' | ConvertTo-Json -Compress"
        )
        completed = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", command],
            cwd=self.workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        config = json.loads(completed.stdout)
        self.assertEqual(
            config["RemoteControllerRoot"],
            "/srv/fake-profile/autoresearch-v2",
        )
        self.assertEqual(
            config["RemoteBridgeEntry"],
            "/srv/fake-profile/autoresearch-v2/run_autoresearch_v2_bridge.sh",
        )


if __name__ == "__main__":
    unittest.main()
