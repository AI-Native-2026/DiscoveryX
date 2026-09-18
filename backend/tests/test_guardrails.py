"""DLP, guardrails and audit tests."""

from __future__ import annotations

import pytest

from app.core import audit, dlp
from app.core.errors import GuardrailViolation
from app.core.guardrails import Guardrails
from app.core.rbac import get_policy


def test_dlp_blocks_internal_project_id():
    result = dlp.scan("please assess internal project PROJ-1234 immediately")
    assert result.blocked
    assert any(f.rule == "internal_project_id" for f in result.findings)


def test_dlp_masks_email():
    result = dlp.scan("contact alice@example.com for details")
    assert result.action == "MASK"
    assert "alice@example.com" not in (result.masked_text or "")
    assert "***" in (result.masked_text or "")


def test_dlp_allows_clean_text():
    assert dlp.scan("design a brain-penetrant inhibitor").action == "ALLOW"


def test_dlp_blocks_biosequence():
    assert dlp.scan("sequence MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ").blocked


def test_guardrails_check_outbound_raises_and_audits():
    g = Guardrails(get_policy())
    sci = get_policy().build_principal("scientist", "alice")
    with pytest.raises(GuardrailViolation) as exc:
        g.check_outbound("PROJ-1234 secret", sci)
    assert exc.value.guardrail == "dlp"
    events = audit.read_events(decision="BLOCKED")
    assert any(e.action == "llm:call" for e in events)


def test_guardrails_masks_and_returns_text():
    g = Guardrails(get_policy())
    sci = get_policy().build_principal("scientist", "alice")
    out = g.check_outbound("email me at bob@example.com", sci)
    assert "bob@example.com" not in out


def test_rbac_denial_audited():
    g = Guardrails(get_policy())
    guest = get_policy().build_principal("guest", "anon")
    with pytest.raises(GuardrailViolation) as exc:
        g.authorize(guest, "task:submit", resource="task")
    assert exc.value.guardrail == "rbac"
    assert any(e.reason.startswith("missing permission") for e in audit.read_events(decision="BLOCKED"))


def test_filter_chunks_by_clearance():
    g = Guardrails(get_policy())
    guest = get_policy().build_principal("guest")
    chunks = [
        {"metadata": {"sensitivity": "public"}},
        {"metadata": {"sensitivity": "confidential"}},
    ]
    kept = g.filter_chunks(chunks, guest)
    assert len(kept) == 1
    assert kept[0]["metadata"]["sensitivity"] == "public"


def test_audit_log_is_jsonl():
    audit.log_decision(actor="t", role="admin", action="x", resource="y", decision="ALLOW", reason="test")
    events = audit.read_events(limit=10)
    assert events
    assert events[0].actor == "t"
