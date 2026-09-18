"""Guardrails — real, enforced security for the platform.

Combines:
  * **RBAC**  — role permissions and data clearance
  * **DLP**   — sensitive-content detection before data leaves the boundary
  * **Audit** — every decision is written to the JSON-Lines audit log

A denial raises :class:`GuardrailViolation` which aborts the workflow.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from app.core import audit, dlp
from app.core.errors import GuardrailViolation
from app.core.logging import get_logger, log_event
from app.core.rbac import Principal, RBACPolicy, get_policy

logger = get_logger("discoveryx.guardrails")


class Guardrails:
    def __init__(self, policy: RBACPolicy | None = None) -> None:
        self.policy = policy or get_policy()

    # ------------------------------------------------------------------ RBAC
    def authorize(self, principal: Principal, permission: str, *, resource: str | None = None) -> None:
        try:
            self.policy.authorize(principal, permission, resource=resource)
        except GuardrailViolation as exc:
            audit.log_decision(
                actor=principal.id,
                role=principal.role,
                action=permission,
                resource=resource or "",
                decision="BLOCKED",
                reason=exc.reason or exc.message,
            )
            log_event(logger, 30, "rbac_denied", actor=principal.id, role=principal.role, permission=permission)
            raise
        audit.log_decision(
            actor=principal.id,
            role=principal.role,
            action=permission,
            resource=resource or "",
            decision="ALLOW",
            reason="rbac ok",
        )

    def authorize_level(self, principal: Principal, level: str, *, resource: str | None = None) -> None:
        try:
            self.policy.authorize_level(principal, level, resource=resource)
        except GuardrailViolation as exc:
            audit.log_decision(
                actor=principal.id,
                role=principal.role,
                action="data:read",
                resource=resource or level,
                decision="BLOCKED",
                reason=exc.reason or exc.message,
            )
            raise
        audit.log_decision(
            actor=principal.id,
            role=principal.role,
            action="data:read",
            resource=resource or level,
            decision="ALLOW",
            reason=f"clearance {principal.clearance} >= {level}",
        )

    def allowed_levels(self, principal: Principal) -> list[str]:
        return self.policy.allowed_levels(principal)

    # ------------------------------------------------------------------- DLP
    def check_outbound(
        self,
        text: str,
        principal: Principal,
        *,
        action: str = "llm:call",
        resource: str = "deepseek",
    ) -> str:
        """DLP-scan text leaving the trust boundary. Returns text (possibly masked).

        Raises :class:`GuardrailViolation` on a BLOCK rule.
        """
        result = dlp.scan(text)
        if result.action == "BLOCK":
            hit = next(f for f in result.findings if f.action == "BLOCK")
            audit.log_decision(
                actor=principal.id,
                role=principal.role,
                action=action,
                resource=resource,
                decision="BLOCKED",
                reason=f"DLP:{hit.rule}",
                matched=hit.match[:32],
            )
            log_event(logger, 30, "dlp_blocked", actor=principal.id, rule=hit.rule, action=action)
            raise GuardrailViolation(
                f"DLP blocked outbound content: rule '{hit.rule}'",
                guardrail="dlp",
                actor=principal.id,
                action=action,
                resource=resource,
                reason=f"{hit.rule}: {hit.match[:32]}",
            )
        if result.action == "MASK":
            audit.log_decision(
                actor=principal.id,
                role=principal.role,
                action=action,
                resource=resource,
                decision="MASKED",
                reason="DLP masked: " + ", ".join(sorted({f.rule for f in result.findings})),
            )
            return result.masked_text or text
        return text

    # ------------------------------------------------------------------ RAG
    def filter_chunks(self, chunks: Sequence[dict[str, Any]], principal: Principal) -> list[dict[str, Any]]:
        """Drop RAG chunks the principal is not cleared to read."""
        allowed = set(self.allowed_levels(principal))
        kept = [c for c in chunks if str(c.get("metadata", {}).get("sensitivity", "public")) in allowed]
        dropped = len(chunks) - len(kept)
        if dropped:
            audit.log_decision(
                actor=principal.id,
                role=principal.role,
                action="rag:filter",
                resource="chroma",
                decision="BLOCKED",
                reason=f"clearance filter dropped {dropped} chunk(s)",
                dropped=dropped,
                allowed_levels=sorted(allowed),
            )
        return kept

    def filter_datasets(self, datasets: Iterable[Any], principal: Principal) -> list[Any]:
        allowed = set(self.allowed_levels(principal))
        return [d for d in datasets if getattr(d, "sensitivity", "public") in allowed]


_guardrails: Guardrails | None = None


def get_guardrails() -> Guardrails:
    global _guardrails
    if _guardrails is None:
        _guardrails = Guardrails()
    return _guardrails


def reset_guardrails() -> None:
    global _guardrails
    _guardrails = None
