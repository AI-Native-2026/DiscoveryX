"""Settings and RBAC policy tests."""

from __future__ import annotations

from app.core.rbac import CLEARANCE_ORDER, Principal, clearance_rank, get_policy


def test_settings_loads_and_redacts():
    from config.settings import get_settings

    s = get_settings()
    red = s.redacted()
    assert red["app"].startswith("DiscoveryX")
    assert "deepseek_api_key" in red


def test_policy_roles_present():
    policy = get_policy()
    for role in ("admin", "scientist", "engineer", "auditor", "guest"):
        assert policy.exists(role)


def test_admin_has_wildcard():
    policy = get_policy()
    admin = policy.build_principal("admin")
    assert admin.can("anything:at:all")


def test_guest_cannot_submit_tasks():
    policy = get_policy()
    guest = policy.build_principal("guest")
    assert not guest.can("task:submit")
    assert guest.can("rag:query")


def test_clearance_ordering():
    assert clearance_rank("public") < clearance_rank("internal") < clearance_rank("confidential") < clearance_rank("restricted")
    assert CLEARANCE_ORDER[-1] == "restricted"


def test_scientist_clearance_allows_internal_but_not_restricted():
    policy = get_policy()
    sci = policy.build_principal("scientist")
    assert policy.can_read_level(sci, "internal")
    assert policy.can_read_level(sci, "confidential")
    assert not policy.can_read_level(sci, "restricted")


def test_unknown_role_falls_back_to_default():
    policy = get_policy()
    p = policy.build_principal("does-not-exist")
    assert p.role == policy.default_role


def test_principal_can_helper():
    p = Principal(id="u", role="engineer", permissions=["task:read"], clearance="internal")
    assert p.can("task:read")
    assert not p.can("task:submit")
