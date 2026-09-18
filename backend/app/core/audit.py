"""Audit log — append-only JSON Lines.

Every authorization decision (allow or block), every guardrail hit and every
external LLM call is recorded with a trace id, giving a real audit trail that
aligns with GxP / ALCOA+ expectations.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.logging import get_trace_id

Decision = Literal["ALLOW", "BLOCKED", "MASKED"]

_lock = threading.Lock()


class AuditEvent(BaseModel):
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds"))
    trace_id: str = Field(default_factory=get_trace_id)
    actor: str = "anonymous"
    role: str = "guest"
    action: str = ""
    resource: str = ""
    decision: Decision = "ALLOW"
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


def _path() -> Path:
    from config.settings import get_settings

    p = get_settings().audit_log_path
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(event: AuditEvent) -> AuditEvent:
    path = _path()
    line = event.model_dump_json()
    with _lock:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return event


def log_decision(
    *,
    actor: str,
    role: str,
    action: str,
    resource: str,
    decision: Decision,
    reason: str = "",
    **details: Any,
) -> AuditEvent:
    return record(
        AuditEvent(
            actor=actor,
            role=role,
            action=action,
            resource=resource,
            decision=decision,
            reason=reason,
            details=details,
        )
    )


def read_events(
    *,
    limit: int = 100,
    offset: int = 0,
    actor: str | None = None,
    decision: Decision | None = None,
) -> list[AuditEvent]:
    path = _path()
    if not path.exists():
        return []
    rows: list[AuditEvent] = []
    with _lock:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                evt = AuditEvent.model_validate_json(line)
            except Exception:  # pragma: no cover - skip corrupt lines
                continue
            if actor and evt.actor != actor:
                continue
            if decision and evt.decision != decision:
                continue
            rows.append(evt)
    rows.sort(key=lambda e: e.ts, reverse=True)
    return rows[offset : offset + limit]


def count_events() -> int:
    path = _path()
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
