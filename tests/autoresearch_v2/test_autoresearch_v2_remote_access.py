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

class AutoresearchV2RemoteAccessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        for relative in (
            "scripts/remote/autoresearch-v2.ps1",
            "scripts/remote/lib/common.ps1",
            "scripts/remote/lib/config.ps1",
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
        completed = subprocess.run(
            [
                "powershell.exe",
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
        self.assertEqual(arguments[-1], "exit")

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
                ["powershell.exe", "-NoProfile", "-Command", command],
                cwd=self.workspace,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertEqual(json.loads(self.scp_log.read_text(encoding="utf-8")), expected)


if __name__ == "__main__":
    unittest.main()
