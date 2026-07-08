#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${AR2_CONTROLLER_PYTHON:-python3}"

export AR2_REMOTE_ROOT="${AR2_REMOTE_ROOT:-${REMOTE_ROOT:-}}"

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/autoresearch_v2_driver.py" "$@"
