"""Data Loss Prevention (DLP).

Scans text for sensitive patterns before it leaves the trust boundary (e.g.
before a call to the external DeepSeek API, or before it is written to a shared
index). ``BLOCK`` findings raise :class:`GuardrailViolation`; ``MASK`` findings
are redacted in place.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.core.errors import GuardrailViolation

DLPAction = Literal["BLOCK", "MASK"]

DEFAULT_RULES: list[dict[str, str]] = [
    {
        "name": "internal_project_id",
        "description": "Internal project identifier",
        "pattern": r"PROJ-\d{4,}",
        "action": "BLOCK",
    },
    {
        "name": "internal_compound_id",
        "description": "Internal compound identifier",
        "pattern": r"CPD-\d{4,}",
        "action": "MASK",
    },
    {
        "name": "email",
        "description": "Email address / PII",
        "pattern": r"[\w.+-]+@[\w-]+\.[\w.-]+",
        "action": "MASK",
    },
    {
        "name": "phone_cn",
        "description": "Chinese mobile number",
        "pattern": r"(?<!\d)1[3-9]\d{9}(?!\d)",
        "action": "MASK",
    },
    {
        "name": "biosequence",
        "description": "Protein / nucleotide sequence",
        "pattern": r"\b[ACDEFGHIKLMNPQRSTVWY]{20,}\b",
        "action": "BLOCK",
    },
]

RULES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "dlp_rules.json"


class DLPRule(BaseModel):
    name: str
    description: str = ""
    pattern: str
    action: DLPAction = "BLOCK"


class DLPFinding(BaseModel):
    rule: str
    description: str = ""
    action: DLPAction
    match: str


class DLPResult(BaseModel):
    action: Literal["ALLOW", "MASK", "BLOCK"] = "ALLOW"
    findings: list[DLPFinding] = Field(default_factory=list)
    masked_text: str | None = None

    @property
    def blocked(self) -> bool:
        return self.action == "BLOCK"


@lru_cache(maxsize=1)
def load_rules() -> list[DLPRule]:
    raw = DEFAULT_RULES
    if RULES_PATH.exists():
        try:
            raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - fall back to defaults
            raw = DEFAULT_RULES
    return [DLPRule(**r) for r in raw]


def scan(text: str, rules: list[DLPRule] | None = None) -> DLPResult:
    """Scan ``text`` and classify the highest-severity action."""
    rules = rules or load_rules()
    findings: list[DLPFinding] = []
    masked = text
    for rule in rules:
        try:
            pattern = re.compile(rule.pattern)
        except re.error:  # pragma: no cover - invalid rule
            continue
        for m in pattern.finditer(text):
            findings.append(
                DLPFinding(rule=rule.name, description=rule.description, action=rule.action, match=m.group(0))
            )
        if rule.action == "MASK":
            masked = pattern.sub(lambda mm: "*" * len(mm.group(0)), masked)

    if any(f.action == "BLOCK" for f in findings):
        action: Literal["ALLOW", "MASK", "BLOCK"] = "BLOCK"
    elif findings:
        action = "MASK"
    else:
        action = "ALLOW"

    return DLPResult(
        action=action,
        findings=findings,
        masked_text=masked if action == "MASK" else None,
    )


def enforce(
    text: str,
    *,
    actor: str | None = None,
    action: str = "llm:call",
    resource: str = "deepseek",
    rules: list[DLPRule] | None = None,
) -> DLPResult:
    """Raise :class:`GuardrailViolation` on BLOCK; otherwise return the result."""
    result = scan(text, rules)
    if result.blocked:
        hit = next(f for f in result.findings if f.action == "BLOCK")
        raise GuardrailViolation(
            f"DLP blocked outbound content: rule '{hit.rule}'",
            guardrail="dlp",
            actor=actor,
            action=action,
            resource=resource,
            reason=f"{hit.rule}: {hit.match[:32]}",
        )
    return result


def redact(text: str, rules: list[DLPRule] | None = None) -> str:
    """Return text with MASK rules applied (never raises)."""
    return scan(text, rules).masked_text or text
