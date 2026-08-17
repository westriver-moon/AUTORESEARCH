from __future__ import annotations

import subprocess
import shutil
import unittest

from support import PROJECT_ROOT

ENTRY = PROJECT_ROOT / "scripts" / "remote" / "autoresearch-v2.ps1"
SMOKE = PROJECT_ROOT / "scripts" / "remote" / "smoke-autoresearch-v2.ps1"
LIBRARY = PROJECT_ROOT / "scripts" / "remote" / "lib" / "autoresearch_v2.ps1"
RUNTIME = PROJECT_ROOT / "scripts" / "remote" / "remote-bin"
CONFIG = PROJECT_ROOT / "config" / "autoresearch-v2.example.psd1"
ACCESS = PROJECT_ROOT / "scripts" / "remote" / "lib" / "remote_access.ps1"
CONFIG_LIBRARY = PROJECT_ROOT / "scripts" / "remote" / "lib" / "config.ps1"
SELECTOR = PROJECT_ROOT / "scripts" / "remote" / "select-profile.ps1"
SELECTOR_UI = PROJECT_ROOT / "scripts" / "remote" / "access" / "select-remote-profile.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell.exe") or "powershell.exe"


class RemoteAutoresearchV2WrapperTest(unittest.TestCase):
    def test_deploy_uses_only_generic_runtime_modules(self) -> None:
        text = ENTRY.read_text(encoding="utf-8")
        for name in (
            "run_autoresearch_v2_bridge.sh",
            "autoresearch_v2_driver.py",
            "autoresearch_v2_common.py",
            "autoresearch_v2_gpu_lease.py",
        ):
            self.assertIn(f'"{name}"', text)
        self.assertNotIn("autoresearch_v2_metric_", text)

    def test_doctor_uploads_and_checks_the_explicit_target(self) -> None:
        text = ENTRY.read_text(encoding="utf-8")
        doctor = text[text.index('"doctor" {') : text.index("default {", text.index('"doctor" {'))]
        self.assertIn("$TargetPath", doctor)
        self.assertIn("Invoke-AutoresearchContractValidation", doctor)
        self.assertIn("validate-target", doctor)
        self.assertIn('"--target", $remoteDoctorTarget', doctor)
        self.assertIn("Copy-AutoresearchToRemote", doctor)

    def test_defaults_and_smoke_are_generic(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in (LIBRARY, CONFIG, SMOKE)
        )
        self.assertIn("autoresearch/program-example.md", combined)
        self.assertIn("autoresearch/targets/example-cpu.yaml", combined)
        self.assertIn("[string] $TargetPath", combined)
        self.assertIn("[string] $ProgramPath", combined)
        for banned in ("TVI-LFM", "SYSU", "PMT", "stage_a", "mAP", "mINP"):
            self.assertNotIn(banned, combined)

    def test_powershell_scripts_parse(self) -> None:
        command = (
            "$errors=$null; "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{ENTRY}',[ref]$null,[ref]$errors); "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{SMOKE}',[ref]$null,[ref]$errors); "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{ACCESS}',[ref]$null,[ref]$errors); "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{CONFIG_LIBRARY}',[ref]$null,[ref]$errors); "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{SELECTOR}',[ref]$null,[ref]$errors); "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{SELECTOR_UI}',[ref]$null,[ref]$errors); "
            "if($errors.Count -gt 0){$errors | ForEach-Object {Write-Error $_}; exit 1}"
        )
        completed = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", command],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_active_generic_runtime_has_no_project_adapter(self) -> None:
        files = [
            ENTRY,
            SMOKE,
            LIBRARY,
            *sorted(RUNTIME.glob("autoresearch_v2_*.py")),
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
        for banned in ("TVI-LFM", "SYSU", "PMT", "Stage A", "stage_a", "mAP", "mINP"):
            self.assertNotIn(banned, combined)


if __name__ == "__main__":
    unittest.main()
