#!/usr/bin/env bash
# Idempotent dependency install for SIMBA. Safe to run more than once.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo -n apt-get update
  sudo -n apt-get install -y python3-venv || sudo -n apt-get install -y python3.12-venv
fi

python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
