#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from autoresearch_v2_contracts import ContractError, load_target_config, validate_target_dict


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate autoresearch v2 target YAML")
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    payload = validate_target_dict(load_target_config(args.path))
    print(json.dumps({"ok": True, "target": payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc
