"""Guardrails API — audit log, policy introspection and DLP demonstration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_principal, guardrails
from app.core import audit, dlp
from app.core.guardrails import Guardrails
from app.core.rbac import Principal, get_policy
from app.models.schemas import (
    DLPDemoRequest,
    DLPDemoResponse,
    GuardrailEventList,
    GuardrailEventOut,
)

router = APIRouter()


@router.get("/guardrails/events", response_model=GuardrailEventList, summary="Query the audit log")
async def list_events(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    decision: str | None = Query(default=None, pattern="^(ALLOW|BLOCKED|MASKED)$"),
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> GuardrailEventList:
    guard.authorize(principal, "audit:read", resource="audit")
    events = audit.read_events(limit=limit, offset=offset, decision=decision)  # type: ignore[arg-type]
    return GuardrailEventList(
        items=[GuardrailEventOut(**e.model_dump()) for e in events],
        total=audit.count_events(),
    )


@router.get("/guardrails/policy", summary="Inspect the RBAC policy")
async def policy_view(
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> dict:
    guard.authorize(principal, "guardrails:read", resource="guardrails")
    policy = get_policy()
    return {
        "default_role": policy.default_role,
        "roles": {
            role: {
                "permissions": policy.permissions_for(role),
                "clearance": policy.clearance_for(role),
            }
            for role in sorted(policy.roles)
        },
        "clearance_levels": ["public", "internal", "confidential", "restricted"],
        "dlp_rules": [r.model_dump() for r in dlp.load_rules()],
    }


@router.post("/guardrails/dlp-check", response_model=DLPDemoResponse, summary="Run a DLP scan")
async def dlp_check(
    request: DLPDemoRequest,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> DLPDemoResponse:
    """Scan text and report whether it would be blocked or masked."""
    guard.authorize(principal, "guardrails:check", resource="guardrails")
    result = dlp.scan(request.text)
    decision = "BLOCKED" if result.blocked else ("MASKED" if result.action == "MASK" else "ALLOW")
    audit.log_decision(
        actor=principal.id,
        role=principal.role,
        action="guardrails:check",
        resource="dlp",
        decision=decision,  # type: ignore[arg-type]
        reason=", ".join(sorted({f.rule for f in result.findings})) or "no rule matched",
    )
    return DLPDemoResponse(
        action=result.action,
        findings=[f.model_dump() for f in result.findings],
        masked_text=result.masked_text,
        blocked=result.blocked,
    )
