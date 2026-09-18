# Security & Governance

DiscoveryX enforces security in the core engine, not in the UI. Denials raise
`GuardrailViolation` and abort the workflow; every decision is written to an
append-only audit log.

## 1. RBAC

`backend/config/rbac_policy.json` maps roles to permissions and to a **data
clearance** level.

| Role | Clearance | Typical permissions |
|---|---|---|
| `admin` | restricted | `*` |
| `scientist` | confidential | `task:submit/read`, `rag:query`, `dataset:read/import`, `copilot:chat`, `approval:read/decide` |
| `engineer` | internal | `dataset:index`, `audit:read`, `task:read`, `copilot:chat`, `approval:read` |
| `auditor` | confidential | `task:read`, `audit:read`, `guardrails:read`, `approval:read` |
| `guest` | public | `rag:query` |

Clearance is ordered `public < internal < confidential < restricted`; dataset
and RAG access is filtered by it. The reference client exposes a **role
switcher** so the behaviour is directly observable (e.g. `guest` cannot submit a
task; a `scientist` cannot read a `restricted` dataset).

## 2. DLP (Data Loss Prevention)

Every piece of text that **leaves the trust boundary** — before an external LLM
call (DeepSeek), before writing to a shared index — is scanned by
`app/core/dlp.py`.

Rules are declarative and inspectable (`GET /api/v1/guardrails/policy`):

| Rule | Pattern | Action |
|---|---|---|
| `internal_project_id` | `PROJ-\d{4,}` | **BLOCK** |
| `internal_compound_id` | `CPD-\d{4,}` | MASK |
| `email` | email address | MASK |
| `phone_cn` | CN mobile number | MASK |
| `biosequence` | protein / nucleotide sequence | **BLOCK** |

* `BLOCK` → raises `GuardrailViolation` (HTTP 403), the workflow aborts, and the
  event is audited as `BLOCKED`.
* `MASK` → the sensitive span is replaced before the call proceeds; audited as
  `MASKED`.

Try it: submitting a task or asking the Copilot a question containing
`PROJ-1234` is rejected with HTTP 403 and recorded in the audit log.

## 3. Approvals (human-in-the-loop)

Actions that should not be automatic raise an **approval request**
(`app/core/approvals.py`). After a DMTA run completes, the platform asks a human
to approve advancing the top candidates to synthesis and assay.

* `GET /api/v1/approvals` — list requests (filter by `status`)
* `POST /api/v1/approvals/{id}/decision` — `approved` / `rejected` (+ comment)

Requests appear in **合规与审计 (Governance)** in the reference client, where a
reviewer can approve or reject with a comment. Decisions are audited
(`approval:decide`).

## 4. Audit log

`app/core/audit.py` appends JSON Lines to `data/audit/audit.jsonl`. Each event
carries `ts`, `trace_id`, `actor`, `role`, `action`, `resource`, `decision`
(`ALLOW` / `BLOCKED` / `MASKED`) and `reason`. The `trace_id` is propagated from
the HTTP request through the async worker and the agent graph, so a full run can
be reconstructed.

This aligns with GxP / ALCOA+ expectations (attributable, legible,
contemporaneous, original, accurate, complete, consistent, enduring, available).

## 5. External model boundary

Only `public` content may be sent to the external model. Internal / confidential
datasets are indexed into separate ChromaDB collections
(`kb_internal_*`, `kb_confidential_*`) and are filtered out of retrieval for
principals without the matching clearance — and DLP blocks any sensitive pattern
that would otherwise leave the boundary.
