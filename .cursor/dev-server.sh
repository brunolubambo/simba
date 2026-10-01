#!/usr/bin/env bash
# Foreground SIMBA API on port 8000.
set -euo pipefail

source "$(dirname "$0")/runtime.sh"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$SIMBA_DEV_ROOT"
exec "$REPO_ROOT/.venv/bin/python" -m uvicorn simba.server:app --host 0.0.0.0 --port 8000
