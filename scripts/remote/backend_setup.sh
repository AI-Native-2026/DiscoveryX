#!/usr/bin/env bash
# Install backend dependencies and run lint + tests.
set -uo pipefail
cd "$HOME/discoveryx/backend" || exit 1

echo "=== create venv ==="
uv venv --python 3.11 .venv 2>&1 | tail -3

echo "=== install deps (this can take a few minutes) ==="
VIRTUAL_ENV=.venv uv pip install -r requirements-dev.txt 2>&1 | tail -12

echo "=== ruff ==="
.venv/bin/ruff check . --output-format=concise 2>&1 | tail -30

echo "=== pytest ==="
.venv/bin/python -m pytest -q 2>&1 | tail -40

echo "=== DONE ==="
