"""Pydantic models for the API and the agent domain."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------- enums
class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class DataType(str, Enum):
    TABULAR = "tabular"
    DOCUMENT = "document"
    STRUCTURE = "structure"
    SEQUENCE = "sequence"
    MIXED = "mixed"


class Purpose(str, Enum):
    RAG = "rag"
    TOOL = "tool"
    FILE = "file"


# ---------------------------------------------------------------- auth
class PrincipalOut(BaseModel):
    id: str
    role: str
    permissions: list[str]
    clearance: str


# ---------------------------------------------------------------- tasks
class TaskRequest(BaseModel):
    hypothesis: str = Field(..., min_length=8, max_length=2000, description="Scientific hypothesis")
    # Left unset they are inherited from the referenced project, so a task runs
    # against its project's target by default.
    target: str | None = Field(default=None, description="Target name; defaults to the project's target")
    pdb_id: str | None = Field(default=None, description="Reference structure PDB id; defaults to the project's")
    rounds: int = Field(default=3, ge=1, le=6, description="DMTA iterations")
    objectives: list[str] = Field(default_factory=lambda: ["BBB", "hepatotoxicity"])
    project: str = Field(default="BACE1")
    sensitivity: Sensitivity = Field(default=Sensitivity.INTERNAL)
    # compound source
    dataset_id: str | None = Field(
        default=None,
        description="Compound dataset directory to seed Design/Test (falls back to built-in MoleculeNet BACE)",
    )
    smiles_column: str | None = Field(default=None, description="Override the SMILES column name")
    activity_column: str | None = Field(default=None, description="Override the activity column name")
    activity_model: Literal["qsar", "knn"] = Field(
        default="qsar", description="qsar: train on the dataset; knn: similarity lookup"
    )
    seed: int = Field(default=42, ge=0, le=99999)


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    cost_usd: float = 0.0

    def merge(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            calls=self.calls + other.calls,
            cost_usd=round(self.cost_usd + other.cost_usd, 6),
        )


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    created_at: str = Field(default_factory=_now)
    trace_id: str | None = None


class TaskState(BaseModel):
    task_id: str
    project: str | None = None
    dataset_id: str | None = None
    target: str | None = None
    objectives: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.QUEUED
    stage: str = "queued"
    round: int = 0
    rounds: int = 0
    progress: float = 0.0
    trace_id: str | None = None
    attempts: int = 0
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    error: str | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    result: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------- dmta domain
class Candidate(BaseModel):
    id: int
    smiles: str
    pIC50: float | None = None
    bbb: bool | None = None
    hepatotoxic: bool | None = None
    solubility: float | None = None
    herg: float | None = None
    sa_score: float | None = None
    qed: float | None = None
    rationale: str | None = None
    route_steps: int | None = None
    route_available: bool | None = None
    mpo: float | None = None


class DMTARound(BaseModel):
    round: int
    candidates: list[Candidate] = Field(default_factory=list)
    passed: int = 0
    summary: str = ""
    decision: str = ""
    action: str = ""
    directives: list[str] = Field(default_factory=list)
    directive_labels: list[str] = Field(default_factory=list)
    # Model-written prose for this round. The pass/fail decision above is
    # deterministic; this only puts the numbers into words.
    narrative: str = ""


class DMTAReport(BaseModel):
    task_id: str
    target: str
    hypothesis: str
    # Model-written target intelligence summary grounded in the PDB entry and
    # the retrieved literature for this run's dataset.
    target_summary: str = ""
    # Which endpoints the run was optimising. Clients use this to show pass/fail
    # only for the objectives that apply to the project.
    objectives: list[str] = Field(default_factory=list)
    rounds: list[DMTARound] = Field(default_factory=list)
    top_candidates: list[Candidate] = Field(default_factory=list)
    decision: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    generated_at: str = Field(default_factory=_now)
    # provenance: which data and models produced this report
    dataset: dict[str, Any] = Field(default_factory=dict)
    activity_model: dict[str, Any] = Field(default_factory=dict)
    admet_engine: str | None = None


# ---------------------------------------------------------------- rag
class RAGQuery(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    collections: list[str] | None = None


class Citation(BaseModel):
    id: str
    title: str
    source: str = "PMC"
    sensitivity: str = "public"
    score: float = 0.0
    snippet: str = ""


class RAGResult(BaseModel):
    query: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    used_chunks: int = 0
    blocked_chunks: int = 0
    # Tokens spent synthesising the answer (zero when no LLM was available).
    token_usage: TokenUsage = Field(default_factory=TokenUsage)


# ---------------------------------------------------------------- datasets
class DatasetInfo(BaseModel):
    id: str
    name: str
    data_type: DataType = DataType.TABULAR
    source: str = ""
    sensitivity: Sensitivity = Sensitivity.PUBLIC
    purpose: Purpose = Purpose.TOOL
    scale: str = ""
    status: str = "ready"
    rag_indexed: bool = False
    path: str | None = None
    owner: str = "system"
    updated_at: str = Field(default_factory=_now)
    meta: dict[str, Any] = Field(default_factory=dict)
    # directory-based datasets
    is_directory: bool = False
    n_files: int = 0
    size_bytes: int = 0
    file_types: dict[str, int] = Field(default_factory=dict)


class DatasetList(BaseModel):
    items: list[DatasetInfo]
    total: int


class DatasetCreate(BaseModel):
    """Register a new dataset directory."""

    id: str = Field(..., pattern=r"^[a-zA-Z0-9_-]{2,64}$", description="Directory name")
    name: str = Field(..., min_length=2, max_length=120)
    data_type: DataType = DataType.DOCUMENT
    source: str = "upload"
    sensitivity: Sensitivity = Sensitivity.PUBLIC
    purpose: Purpose = Purpose.RAG
    description: str = ""


class DatasetFile(BaseModel):
    name: str
    rel_path: str
    ext: str
    size_bytes: int
    modified_at: str


class DatasetFileList(BaseModel):
    dataset_id: str
    items: list[DatasetFile]
    total: int
    file_types: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------- copilot
class CopilotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CopilotRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    task_id: str | None = Field(default=None, description="Optional task for run context")
    history: list[CopilotMessage] = Field(default_factory=list, max_length=20)


class CopilotStep(BaseModel):
    tool: str
    detail: str = ""
    status: str = "ok"


class CopilotReply(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    steps: list[CopilotStep] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    blocked: bool = False


# ---------------------------------------------------------------- guardrails
class GuardrailEventOut(BaseModel):
    ts: str
    trace_id: str
    actor: str
    role: str
    action: str
    resource: str
    decision: Literal["ALLOW", "BLOCKED", "MASKED"]
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class GuardrailEventList(BaseModel):
    items: list[GuardrailEventOut]
    total: int


class DLPDemoRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class DLPDemoResponse(BaseModel):
    action: Literal["ALLOW", "MASK", "BLOCK"]
    findings: list[dict[str, Any]]
    masked_text: str | None = None
    blocked: bool


# ---------------------------------------------------------------- projects
class ProjectOut(BaseModel):
    id: str
    name: str
    description: str = ""
    target: str = "BACE1"
    pdb_id: str = "4WY1"
    objectives: list[str] = Field(default_factory=list)
    created_by: str = "system"
    created_at: str = ""


class ProjectList(BaseModel):
    items: list[ProjectOut]
    total: int


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    target: str = Field(default="BACE1", max_length=40)
    pdb_id: str = Field(default="4WY1", max_length=10)
    objectives: list[str] = Field(default_factory=lambda: ["BBB", "hepatotoxicity"])
    id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{2,40}$")


# ---------------------------------------------------------------- approvals
class ApprovalOut(BaseModel):
    id: str
    task_id: str = ""
    kind: str = "generic"
    title: str = ""
    detail: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "approved", "rejected"] = "pending"
    requested_by: str = "system"
    requested_at: str = ""
    decided_by: str | None = None
    decided_at: str | None = None
    comment: str | None = None


class ApprovalList(BaseModel):
    items: list[ApprovalOut]
    total: int
    pending: int


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------- misc
class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    version: str
    environment: str
    components: dict[str, str] = Field(default_factory=dict)
