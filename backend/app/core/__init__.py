"""Core engine — no web-framework dependencies."""

from app.core.errors import DiscoveryXError, GuardrailViolation

__all__ = ["DiscoveryXError", "GuardrailViolation"]
