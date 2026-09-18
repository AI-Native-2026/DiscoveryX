"""Approvals API — human-in-the-loop review of workflow outputs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_principal, guardrails
from app.core import approvals
from app.core.guardrails import Guardrails
from app.core.rbac import Principal
from app.models.schemas import ApprovalDecision, ApprovalList, ApprovalOut

router = APIRouter()


@router.get("/approvals", response_model=ApprovalList, summary="List approval requests")
async def list_approvals(
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
    task_id: str | None = Query(default=None),
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> ApprovalList:
    guard.authorize(principal, "approval:read", resource="approval")
    rows = approvals.list_requests(status=status, task_id=task_id)  # type: ignore[arg-type]
    return ApprovalList(
        items=[ApprovalOut(**r.model_dump()) for r in rows],
        total=len(rows),
        pending=len(approvals.list_requests(status="pending")),
    )


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalOut, summary="Approve or reject")
async def decide(
    approval_id: str,
    request: ApprovalDecision,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> ApprovalOut:
    guard.authorize(principal, "approval:decide", resource=f"approval:{approval_id}")
    result = approvals.decide(
        approval_id,
        decision=request.decision,
        actor=principal.id,
        role=principal.role,
        comment=request.comment,
    )
    return ApprovalOut(**result.model_dump())
