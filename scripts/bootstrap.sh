#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install -e '.[dev,rollout,persistent]'
.venv/bin/python scripts/smoke_contracts.py
echo 'Harness ready. Configure external policy/simulator runtimes before live evaluation.'
