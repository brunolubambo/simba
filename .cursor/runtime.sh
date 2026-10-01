#!/usr/bin/env bash
# Lay out SIMBA the way the code expects: a package named simba whose parent
# holds pwa/, data/ and workspace/. Source this file; do not execute it alone.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export SIMBA_DEV_ROOT="${SIMBA_DEV_ROOT:-$HOME/simba-dev}"
export SIMBA_TOKEN="${SIMBA_TOKEN:-dev-simba-token}"
export OBSERVER_ENABLED="${OBSERVER_ENABLED:-false}"
export PYTHONPATH="${SIMBA_DEV_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$SIMBA_DEV_ROOT/simba" "$SIMBA_DEV_ROOT/pwa" "$SIMBA_DEV_ROOT/data" "$SIMBA_DEV_ROOT/workspace"

if ! mountpoint -q "$SIMBA_DEV_ROOT/simba"; then
  sudo -n mount --bind "$REPO_ROOT" "$SIMBA_DEV_ROOT/simba"
fi

cp "$REPO_ROOT/.cursor/pwa/index.html" "$SIMBA_DEV_ROOT/pwa/index.html"
