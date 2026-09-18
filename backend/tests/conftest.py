"""Pytest fixtures — isolate storage and avoid external services."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point all storage at a temp dir and reset cached singletons."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RAW_DIR", str(tmp_path / "data" / "raw"))
    monkeypatch.setenv("DATASETS_DIR", str(tmp_path / "data" / "datasets"))
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "data" / "chroma"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "data" / "audit" / "audit.jsonl"))
    monkeypatch.setenv("RBAC_POLICY_PATH", str(BACKEND_DIR / "config" / "rbac_policy.json"))
    monkeypatch.setenv("ALLOW_HEADER_ROLE", "true")
    monkeypatch.setenv("LOG_JSON", "false")
    # never hit the real LLM from tests
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")

    from config.settings import reset_settings_cache

    reset_settings_cache()
    from app.core.guardrails import reset_guardrails

    reset_guardrails()
    from app.core.rbac import load_policy

    load_policy.cache_clear()
    yield
    reset_settings_cache()


@pytest.fixture
def client() -> TestClient:
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def fake_queue(monkeypatch):
    """Replace Redis-backed task storage with an in-memory dict."""
    from app.tasks import queue

    store: dict[str, object] = {}

    async def save_state(state):  # type: ignore[no-untyped-def]
        store[state.task_id] = state

    async def load_state(task_id):  # type: ignore[no-untyped-def]
        return store.get(task_id)

    async def index_task(task_id):  # type: ignore[no-untyped-def]
        return None

    async def list_task_ids(limit=50):  # type: ignore[no-untyped-def]
        return [k for k in store if not str(k).startswith("_")][:limit]

    async def enqueue_dmta_task(task_id, payload, trace_id):  # type: ignore[no-untyped-def]
        store.setdefault("_enqueued", []).append((task_id, payload, trace_id))  # type: ignore[union-attr]

    monkeypatch.setattr(queue, "save_state", save_state)
    monkeypatch.setattr(queue, "load_state", load_state)
    monkeypatch.setattr(queue, "index_task", index_task)
    monkeypatch.setattr(queue, "list_task_ids", list_task_ids)
    monkeypatch.setattr(queue, "enqueue_dmta_task", enqueue_dmta_task)
    return store
