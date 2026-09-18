"""Shared FastAPI dependencies: authentication/principal and guardrails."""

from __future__ import annotations

from fastapi import Header

from app.core.guardrails import Guardrails, get_guardrails
from app.core.rbac import Principal, get_policy


async def get_principal(
    x_role: str | None = Header(default=None, alias="X-Role", description="Role for RBAC (dev header auth)"),
    x_user: str | None = Header(default=None, alias="X-User", description="Actor identifier"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key", description="Admin API key"),
) -> Principal:
    """Resolve the request principal.

    Production would validate a JWT/OIDC token here; the reference client uses a
    simple ``X-Role``/``X-User`` scheme plus an optional admin API key so that
    RBAC behaviour is demonstrable end to end.
    """
    from config.settings import get_settings

    settings = get_settings()
    policy = get_policy()

    if x_api_key and settings.admin_api_key and x_api_key == settings.admin_api_key:
        return policy.build_principal("admin", x_user or "admin")

    role = x_role if (settings.allow_header_role and x_role) else policy.default_role
    return policy.build_principal(role, x_user or "anonymous")


def guardrails() -> Guardrails:
    return get_guardrails()
