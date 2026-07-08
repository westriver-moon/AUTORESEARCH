#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from autoresearch_v2_contracts import ContractError, load_program_front_matter, validate_program_dict


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate autoresearch v2 program.md")
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    payload = validate_program_dict(load_program_front_matter(args.path))
    print(json.dumps({"ok": True, "program": payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc
