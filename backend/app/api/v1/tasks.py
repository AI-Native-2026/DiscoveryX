"""Task API — submit asynchronous DMTA workflows and poll their state."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from app.api.deps import get_principal, guardrails
from app.core import projects
from app.core.errors import NotFoundError
from app.core.guardrails import Guardrails
from app.core.logging import get_logger, get_trace_id
from app.core.rbac import Principal
from app.models.schemas import TaskRequest, TaskResponse, TaskState, TaskStatus
from app.tasks import queue

logger = get_logger("discoveryx.api.tasks")

router = APIRouter()


@router.post("/tasks", response_model=TaskResponse, status_code=202, summary="Submit a DMTA workflow")
async def create_task(
    request: TaskRequest,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> TaskResponse:
    """Validate, DLP-scan and enqueue a DMTA workflow. Returns a task id."""
    guard.authorize(principal, "task:submit", resource="task")
    # The hypothesis may leave the trust boundary (external LLM), so DLP-check it now.
    guard.check_outbound(request.hypothesis, principal, action="task:submit", resource="task")

    # Pre-flight: the compound source must be usable (SMILES + continuous activity).
    from app.core.taskdata import validate_compound_source

    payload = request.model_dump(mode="json")

    # A task belongs to a project, so it inherits the project's target and
    # reference structure unless the caller overrides them explicitly.
    project = projects.get(request.project) if request.project else None
    payload["target"] = request.target or (project.target if project else None) or "BACE1"
    payload["pdb_id"] = request.pdb_id or (project.pdb_id if project else None) or "4WY1"

    data_source = validate_compound_source(payload, principal, guard)

    task_id = f"task-{uuid.uuid4().hex[:8]}"
    trace_id = get_trace_id()
    state = queue.new_task_state(
        task_id,
        request.rounds,
        trace_id,
        project=request.project or None,
        dataset_id=request.dataset_id or None,
        target=payload["target"],
        objectives=request.objectives,
    )
    await queue.save_state(state)
    await queue.index_task(task_id)
    payload["_principal"] = {"id": principal.id, "role": principal.role}
    payload["_data_source"] = data_source
    await queue.enqueue_dmta_task(task_id, payload, trace_id)

    logger.info("task submitted", extra={"extra_fields": {"task_id": task_id, "target": request.target}})
    return TaskResponse(task_id=task_id, status=TaskStatus.QUEUED, trace_id=trace_id)


@router.get("/tasks", response_model=list[TaskState], summary="List recent tasks")
async def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    project: str | None = Query(default=None, description="Filter by project id"),
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> list[TaskState]:
    guard.authorize(principal, "task:read", resource="task")
    ids = await queue.list_task_ids(limit * 3 if project else limit)
    states: list[TaskState] = []
    for tid in ids:
        st = await queue.load_state(tid)
        if st is None:
            continue
        if project and st.project != project:
            continue
        states.append(st)
        if len(states) >= limit:
            break
    return states


@router.get("/tasks/{task_id}", response_model=TaskState, summary="Get task state")
async def get_task(
    task_id: str,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> TaskState:
    guard.authorize(principal, "task:read", resource="task")
    state = await queue.load_state(task_id)
    if state is None:
        raise NotFoundError(f"task '{task_id}' not found", task_id=task_id)
    return state


@router.get("/tasks/{task_id}/report", response_class=HTMLResponse, summary="Render the DMTA report (HTML)")
async def get_task_report(
    task_id: str,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> HTMLResponse:
    """Self-contained, print-ready HTML report (structures, charts, tables, bill)."""
    guard.authorize(principal, "task:read", resource="task")
    state = await queue.load_state(task_id)
    if state is None:
        raise NotFoundError(f"task '{task_id}' not found", task_id=task_id)
    if not state.result:
        raise NotFoundError(f"task '{task_id}' has no report yet", task_id=task_id, status=state.status.value)

    from app.core.report import render_report_html

    html_doc = render_report_html(state.result, state.model_dump(mode="json"))
    return HTMLResponse(content=html_doc)
