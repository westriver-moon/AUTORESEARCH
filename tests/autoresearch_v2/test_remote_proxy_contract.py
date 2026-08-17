from __future__ import annotations

import unittest

from support import PROJECT_ROOT

CONFIG = PROJECT_ROOT / "config" / "autoresearch-v2.example.psd1"
ENTRY = PROJECT_ROOT / "scripts" / "remote" / "autoresearch-v2.ps1"
ACCESS = PROJECT_ROOT / "scripts" / "remote" / "lib" / "remote_access.ps1"


class RemoteAccessContractTest(unittest.TestCase):
    def test_autoresearch_config_owns_access_and_runtime_settings(self) -> None:
        text = CONFIG.read_text(encoding="utf-8")
        for setting in (
            "RemoteProfiles",
            "RemoteHost",
            "SshConfigPath",
            "ConnectTimeoutSec",
            "ProxyMode",
            "LocalProxyPort",
            "ProxyPort",
            "ProxyProbeUrl",
            "RemoteControllerRoot",
            "RemoteBridgeEntry",
        ):
            self.assertIn(setting, text)

    def test_remote_access_layer_owns_transport_and_proxy(self) -> None:
        text = ACCESS.read_text(encoding="utf-8")
        for function in (
            "Get-AutoresearchRemoteAccess",
            "Invoke-AutoresearchRemoteCommand",
            "Copy-AutoresearchToRemote",
            "Copy-AutoresearchFromRemote",
            "Test-AutoresearchRemoteHttpProxy",
            "Test-AutoresearchRemoteAccess",
            "Ensure-AutoresearchRemoteAccess",
        ):
            self.assertIn(f"function {function}", text)
        self.assertIn('"--proxy"', text)
        self.assertIn('"--head"', text)

    def test_controller_consumes_access_context_only(self) -> None:
        text = ENTRY.read_text(encoding="utf-8")
        self.assertIn("Get-AutoresearchRemoteAccess", text)
        self.assertIn('"access-doctor"', text)
        self.assertIn('"access-ensure"', text)
        self.assertIn("Copy-AutoresearchToRemote", text)
        self.assertNotIn("Invoke-RemoteSsh", text)
        self.assertNotIn("Invoke-RemoteScp", text)
        self.assertNotIn('"lib\\ssh.ps1"', text)

    def test_controller_resolves_runtime_from_the_selected_profile(self) -> None:
        text = ENTRY.read_text(encoding="utf-8")
        self.assertIn("$remoteAccess.SelectedRemoteProfile", text)
        self.assertIn("-RemoteProfile $selectedRemoteProfile", text)

if __name__ == "__main__":
    unittest.main()
