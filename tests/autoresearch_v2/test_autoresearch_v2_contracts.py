from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from support import PROJECT_ROOT

PROGRAM_PATH = PROJECT_ROOT / "autoresearch" / "program-example.md"
TARGET_PATH = PROJECT_ROOT / "autoresearch" / "targets" / "example-cpu.yaml"
CONTRACTS_PATH = PROJECT_ROOT / ".agents" / "skills" / "codex-autoresearch-v2" / "scripts" / "autoresearch_v2_contracts.py"


def load_contracts_module():
    spec = importlib.util.spec_from_file_location("autoresearch_v2_contracts", CONTRACTS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutoresearchV2ContractsTest(unittest.TestCase):
    def test_generic_examples_validate(self) -> None:
        module = load_contracts_module()
        program = module.validate_program_dict(module.load_program_front_matter(PROGRAM_PATH))
        target = module.validate_target_dict(module.load_target_config(TARGET_PATH))
        self.assertEqual(program["direction"], "higher")
        self.assertEqual(target["schema_version"], 2)
        self.assertEqual(target["run"]["argv"][:2], ["python", "-c"])
        self.assertEqual(target["metric"]["primary_key"], "primary_metric")
        self.assertEqual(target["gpu"]["mode"], "none")

    def test_old_or_missing_schema_is_rejected_explicitly(self) -> None:
        module = load_contracts_module()
        raw = yaml.safe_load(TARGET_PATH.read_text(encoding="utf-8"))
        for version in (None, 1, "2"):
            candidate = dict(raw)
            if version is None:
                candidate.pop("schema_version", None)
            else:
                candidate["schema_version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(module.ContractError, "unsupported-schema"):
                module.validate_target_dict(candidate)

    def test_paths_are_contained_and_argv_is_an_array(self) -> None:
        module = load_contracts_module()
        raw = yaml.safe_load(TARGET_PATH.read_text(encoding="utf-8"))
        for mutation in (
            lambda item: item["run"].update({"cwd": "../escape"}),
            lambda item: item.update({"artifacts": ["../../secret"]}),
            lambda item: item.update({"provenance": {"inputs": ["/absolute"]}}),
            lambda item: item["run"].update({"argv": "python task.py"}),
        ):
            candidate = yaml.safe_load(yaml.safe_dump(raw))
            mutation(candidate)
            with self.assertRaises(module.ContractError):
                module.validate_target_dict(candidate)

    def test_metric_values_are_not_restricted_to_unit_interval(self) -> None:
        module = load_contracts_module()
        self.assertEqual(module.ensure_finite_number(73.42, "metric"), 73.42)
        self.assertEqual(module.ensure_finite_number(-5, "metric"), -5.0)
        for value in (math.inf, -math.inf, math.nan, True, "1"):
            with self.subTest(value=value), self.assertRaises(module.ContractError):
                module.ensure_finite_number(value, "metric")

    def test_contract_cli_and_error_code(self) -> None:
        for command, path, key in (
            ("validate-program", PROGRAM_PATH, "program"),
            ("validate-target", TARGET_PATH, "target"),
        ):
            completed = subprocess.run(
                ["python", str(CONTRACTS_PATH), command, "--path", str(path)],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["ok"])
            self.assertIn(key, payload)

        with tempfile.TemporaryDirectory() as temporary:
            legacy = Path(temporary) / "legacy.yaml"
            legacy.write_text("name: legacy\n", encoding="utf-8")
            completed = subprocess.run(
                ["python", str(CONTRACTS_PATH), "validate-target", "--path", str(legacy)],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("unsupported-schema", json.loads(completed.stdout)["error"])

if __name__ == "__main__":
    unittest.main()
