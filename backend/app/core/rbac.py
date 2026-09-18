"""Role-based access control.

Web-framework-free: the API layer resolves an actor/role from the request and
builds a :class:`Principal`; the core enforces permissions and data clearance,
raising :class:`GuardrailViolation` on denial.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.errors import GuardrailViolation

CLEARANCE_ORDER = ["public", "internal", "confidential", "restricted"]


def clearance_rank(level: str) -> int:
    try:
        return CLEARANCE_ORDER.index(level)
    except ValueError:
        return 0


class Principal(BaseModel):
    """The authenticated actor making a request."""

    id: str
    role: str
    permissions: list[str] = Field(default_factory=list)
    clearance: str = "public"

    @property
    def clearance_rank(self) -> int:
        return clearance_rank(self.clearance)

    def can(self, permission: str) -> bool:
        return "*" in self.permissions or permission in self.permissions


class RBACPolicy:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._data = json.loads(self.path.read_text(encoding="utf-8"))
        self.roles: dict[str, dict] = self._data.get("roles", {})
        self.default_role: str = self._data.get("default_role", "guest")

    def exists(self, role: str) -> bool:
        return role in self.roles

    def permissions_for(self, role: str) -> list[str]:
        return list(self.roles.get(role, {}).get("permissions", []))

    def clearance_for(self, role: str) -> str:
        return self.roles.get(role, {}).get("clearance", "public")

    def build_principal(self, role: str, actor_id: str = "anonymous") -> Principal:
        if not self.exists(role):
            role = self.default_role
        return Principal(
            id=actor_id,
            role=role,
            permissions=self.permissions_for(role),
            clearance=self.clearance_for(role),
        )

    def authorize(self, principal: Principal, permission: str, *, resource: str | None = None) -> None:
        """Raise :class:`GuardrailViolation` if the principal lacks ``permission``."""
        if not principal.can(permission):
            raise GuardrailViolation(
                f"RBAC denied: role '{principal.role}' lacks '{permission}'",
                guardrail="rbac",
                actor=principal.id,
                action=permission,
                resource=resource,
                reason=f"missing permission {permission}",
            )

    def authorize_level(self, principal: Principal, level: str, *, resource: str | None = None) -> None:
        """Raise if the principal's clearance is below ``level``."""
        if principal.clearance_rank < clearance_rank(level):
            raise GuardrailViolation(
                f"RBAC denied: role '{principal.role}' clearance '{principal.clearance}' < '{level}'",
                guardrail="rbac",
                actor=principal.id,
                action="data:read",
                resource=resource or level,
                reason=f"insufficient clearance for {level}",
            )

    def can_read_level(self, principal: Principal, level: str) -> bool:
        return principal.clearance_rank >= clearance_rank(level)

    def allowed_levels(self, principal: Principal) -> list[str]:
        return [lvl for lvl in CLEARANCE_ORDER if self.can_read_level(principal, lvl)]


@lru_cache(maxsize=4)
def load_policy(path: str | Path) -> RBACPolicy:
    return RBACPolicy(path)


def get_policy() -> RBACPolicy:
    from config.settings import get_settings

    return load_policy(str(get_settings().rbac_policy_path))
