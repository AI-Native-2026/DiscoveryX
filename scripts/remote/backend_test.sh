#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/discoveryx/backend" || exit 1
echo "=== ruff ==="
.venv/bin/ruff check . --output-format=concise 2>&1 | tail -40
echo
echo "=== pytest ==="
.venv/bin/python -m pytest -q 2>&1 | tail -25
