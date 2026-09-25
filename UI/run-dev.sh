#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
campaign_root="${1:-$script_dir/../runs/formal-four-v17-native}"
port="${PORT:-8766}"

exec python3 "$script_dir/monitor_dashboard.py" \
  --root "$campaign_root" \
  --asset-dir "$script_dir" \
  --host 127.0.0.1 \
  --port "$port" \
  --interval 3
