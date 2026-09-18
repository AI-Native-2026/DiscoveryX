"""Domain errors.

``GuardrailViolation`` is the signal that a security guardrail really blocked a
workflow — it propagates out of the core (which has no web dependency) and is
translated to an HTTP response at the API boundary.
"""

from __future__ import annotations

from typing import Any


class DiscoveryXError(Exception):
    """Base class for all DiscoveryX errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, "details": self.details}


class GuardrailViolation(DiscoveryXError):
    """Raised when RBAC or DLP blocks an action. Always audited."""

    status_code = 403
    code = "guardrail_violation"

    def __init__(
        self,
        message: str,
        *,
        guardrail: str = "unknown",
        actor: str | None = None,
        action: str | None = None,
        resource: str | None = None,
        reason: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            guardrail=guardrail,
            actor=actor,
            action=action,
            resource=resource,
            reason=reason,
            trace_id=trace_id,
        )
        self.guardrail = guardrail
        self.actor = actor
        self.action = action
        self.resource = resource
        self.reason = reason
        self.trace_id = trace_id


class NotFoundError(DiscoveryXError):
    status_code = 404
    code = "not_found"


class ValidationError(DiscoveryXError):
    status_code = 422
    code = "validation_error"


class ConfigurationError(DiscoveryXError):
    status_code = 500
    code = "configuration_error"


class ExternalServiceError(DiscoveryXError):
    status_code = 502
    code = "external_service_error"
