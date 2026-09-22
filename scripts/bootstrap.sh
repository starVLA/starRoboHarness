#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VENV=${STARROBOHARNESS_VENV:-"$ROOT/.venv"}
PYTHON=${PYTHON:-python3}

command -v "$PYTHON" >/dev/null 2>&1 || {
  echo "Python 3 is required (3.10+ recommended)." >&2
  exit 1
}

"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -e "$ROOT[dev]"
"$VENV/bin/python" "$ROOT/scripts/smoke_contracts.py"
"$VENV/bin/python" "$ROOT/examples/minimal_loop.py"

echo
echo "StarRoboHarness is ready."
echo "Activate with: source \"$VENV/bin/activate\""
echo "Run tests with: pytest -q"
