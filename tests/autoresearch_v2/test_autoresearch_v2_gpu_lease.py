from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from support import PROJECT_ROOT

REMOTE_BIN = PROJECT_ROOT / "scripts" / "remote" / "remote-bin"
if str(REMOTE_BIN) not in sys.path:
    sys.path.insert(0, str(REMOTE_BIN))

import autoresearch_v2_gpu_lease as gpu_lease


class AutoresearchV2GpuLeaseTest(unittest.TestCase):
    def test_explicit_selector_limits_nvidia_smi_query(self) -> None:
        completed = SimpleNamespace(
            returncode=0,
            stdout="1, 14, 0\n2, 14, 0\n",
            stderr="",
        )
        with patch.object(gpu_lease.subprocess, "run", return_value=completed) as run:
            rows = gpu_lease._query_gpus("1,2")

        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["nvidia-smi", "-i", "1,2"])
        self.assertEqual([row["id"] for row in rows], ["1", "2"])

    def test_auto_selector_queries_inventory(self) -> None:
        completed = SimpleNamespace(
            returncode=0,
            stdout="0, 14, 0\n",
            stderr="",
        )
        with patch.object(gpu_lease.subprocess, "run", return_value=completed) as run:
            gpu_lease._query_gpus("auto")

        command = run.call_args.args[0]
        self.assertNotIn("-i", command)


if __name__ == "__main__":
    unittest.main()
