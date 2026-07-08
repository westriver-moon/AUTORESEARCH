from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROGRAM_PATH = PROJECT_ROOT / "autoresearch" / "program.md"
TARGET_PATH = PROJECT_ROOT / "autoresearch" / "targets" / "tvilfm-stage-a.yaml"
CONTRACTS_PATH = PROJECT_ROOT / ".agents" / "skills" / "codex-autoresearch-v2" / "scripts" / "autoresearch_v2_contracts.py"
PROGRAM_VALIDATE = PROJECT_ROOT / ".agents" / "skills" / "codex-autoresearch-v2" / "scripts" / "autoresearch_program_validate.py"
TARGET_VALIDATE = PROJECT_ROOT / ".agents" / "skills" / "codex-autoresearch-v2" / "scripts" / "autoresearch_target_validate.py"


def load_contracts_module():
    spec = importlib.util.spec_from_file_location("autoresearch_v2_contracts", CONTRACTS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutoresearchV2ContractsTest(unittest.TestCase):
    def test_program_front_matter_validates(self) -> None:
        module = load_contracts_module()
        payload = module.validate_program_dict(module.load_program_front_matter(PROGRAM_PATH))
        self.assertEqual(payload["direction"], "higher")
        self.assertGreaterEqual(payload["worker_count"], 1)
        self.assertIn("TVI-LFM/main.py", payload["mutable_paths"])

    def test_target_yaml_validates(self) -> None:
        module = load_contracts_module()
        payload = module.validate_target_dict(module.load_target_config(TARGET_PATH))
        self.assertEqual(payload["run"]["metric"]["parser"], "tvilfm_reid")
        self.assertEqual(payload["run"]["metric"]["direction"], "higher")
        self.assertEqual(payload["repo"]["remote_root"], "/home/cgv841/ybj")
        self.assertEqual(payload["run"]["cwd"], "TVI-LFM")
        self.assertIn("TVI-LFM/core/train.py", payload["repo"]["mutable_paths"])

    def test_validator_scripts_exit_zero(self) -> None:
        completed_program = subprocess.run(
            ["python", str(PROGRAM_VALIDATE), "--path", str(PROGRAM_PATH)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed_program.returncode, 0, completed_program.stdout + completed_program.stderr)
        program_payload = json.loads(completed_program.stdout)
        self.assertTrue(program_payload["ok"])

        completed_target = subprocess.run(
            ["python", str(TARGET_VALIDATE), "--path", str(TARGET_PATH)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed_target.returncode, 0, completed_target.stdout + completed_target.stderr)
        target_payload = json.loads(completed_target.stdout)
        self.assertTrue(target_payload["ok"])
