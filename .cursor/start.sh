#!/usr/bin/env bash
# Per-boot setup. Confirms the package imports, then returns. The server itself
# runs in the simba-server terminal.
set -euo pipefail

source "$(dirname "$0")/runtime.sh"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# The repo root is the simba package. Running Python from there puts a local
# telegram.py ahead of the python-telegram-bot distribution.
cd "$SIMBA_DEV_ROOT"
"$REPO_ROOT/.venv/bin/python" -c "import simba.server; print('simba server import ok')"
