# DiscoveryX — common developer and operations tasks.
#
#   make setup     install backend + frontend dependencies
#   make data      build the datasets from public sources (adds the RAG index)
#   make dev-api   run the API with reload
#   make dev-web   run the Vite dev server
#   make worker    run the async worker
#   make test      ruff + pytest + frontend type-check/build
#   make build     production frontend build
#   make deploy    full deploy on this host (see scripts/deploy.sh)
#   make clean     remove caches and build output

SHELL := /bin/bash
APP_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VENV := $(APP_DIR)/backend/.venv
PY := $(VENV)/bin/python
PORT ?= 8000
WEB_PORT ?= 8080

.PHONY: help setup data dev-api dev-web worker test lint build deploy clean

help:
	@grep -E '^#   ' $(MAKEFILE_LIST) | sed 's/^#   //'

setup:
	python3 -m venv $(VENV) 2>/dev/null || true
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r backend/requirements-dev.txt
	cd frontend && { npm ci --silent 2>/dev/null || npm install --silent; }

data:
	$(PY) data/download_data.py --index

dev-api:
	cd backend && ../$(VENV)/bin/uvicorn app.main:app --reload --port $(PORT)

dev-web:
	cd frontend && npm run dev

worker:
	cd backend && ../$(VENV)/bin/arq app.tasks.worker.WorkerSettings

lint:
	cd backend && $(VENV)/bin/ruff check .

test: lint
	cd backend && $(VENV)/bin/pytest -q
	cd frontend && npm run build

build:
	cd frontend && npm run build

deploy:
	bash scripts/deploy.sh

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.pytest_cache backend/.ruff_cache frontend/dist frontend/node_modules/.vite
