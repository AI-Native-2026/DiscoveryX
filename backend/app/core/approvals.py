"""Human-in-the-loop approvals.

Long-running workflows (and any action that touches a shared system) can raise an
**approval request**. Requests are stored on disk, surfaced in the governance
console and decided by a human; every decision is written to the audit log.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core import audit
from app.core.errors import NotFoundError
from app.core.logging import get_logger

logger = get_logger("discoveryx.approvals")

ApprovalStatus = Literal["pending", "approved", "rejected"]

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: f"appr-{uuid.uuid4().hex[:8]}")
    task_id: str = ""
    kind: str = "generic"
    title: str = ""
    detail: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = "pending"
    requested_by: str = "system"
    requested_at: str = Field(default_factory=_now)
    decided_by: str | None = None
    decided_at: str | None = None
    comment: str | None = None


def _path() -> Path:
    from config.settings import get_settings

    p = get_settings().data_dir / "approvals.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> list[ApprovalRequest]:
    p = _path()
    if not p.exists():
        return []
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover
        return []
    out: list[ApprovalRequest] = []
    for r in rows:
        try:
            out.append(ApprovalRequest.model_validate(r))
        except Exception:  # noqa: BLE001
            continue
    return out


def _save(rows: list[ApprovalRequest]) -> None:
    _path().write_text(
        json.dumps([r.model_dump(mode="json") for r in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create(
    *,
    task_id: str,
    kind: str,
    title: str,
    detail: str = "",
    payload: dict[str, Any] | None = None,
    requested_by: str = "system",
) -> ApprovalRequest:
    req = ApprovalRequest(
        task_id=task_id,
        kind=kind,
        title=title,
        detail=detail,
        payload=payload or {},
        requested_by=requested_by,
    )
    with _lock:
        rows = _load()
        rows.append(req)
        _save(rows)
    audit.log_decision(
        actor=requested_by,
        role="system",
        action="approval:request",
        resource=req.id,
        decision="ALLOW",
        reason=kind,
        task_id=task_id,
    )
    logger.info("approval requested %s (%s)", req.id, kind)
    return req


def list_requests(*, status: ApprovalStatus | None = None, task_id: str | None = None) -> list[ApprovalRequest]:
    rows = _load()
    if status:
        rows = [r for r in rows if r.status == status]
    if task_id:
        rows = [r for r in rows if r.task_id == task_id]
    rows.sort(key=lambda r: r.requested_at, reverse=True)
    return rows


def get(approval_id: str) -> ApprovalRequest | None:
    for r in _load():
        if r.id == approval_id:
            return r
    return None


def decide(
    approval_id: str,
    *,
    decision: Literal["approved", "rejected"],
    actor: str,
    role: str = "scientist",
    comment: str | None = None,
) -> ApprovalRequest:
    with _lock:
        rows = _load()
        target: ApprovalRequest | None = None
        for r in rows:
            if r.id == approval_id:
                if r.status != "pending":
                    return r
                r.status = decision
                r.decided_by = actor
                r.decided_at = _now()
                r.comment = comment
                target = r
                break
        if target is None:
            raise NotFoundError(f"approval '{approval_id}' not found", approval_id=approval_id)
        _save(rows)

    audit.log_decision(
        actor=actor,
        role=role,
        action="approval:decide",
        resource=approval_id,
        decision="ALLOW" if decision == "approved" else "BLOCKED",
        reason=f"{decision}: {target.kind}",
        task_id=target.task_id,
        comment=comment,
    )
    logger.info("approval %s %s by %s", approval_id, decision, actor)
    return target


def reset() -> None:
    """Clear all approval requests (used by tests)."""
    with _lock:
        _save([])
