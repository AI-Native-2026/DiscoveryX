"""Project API — create and list discovery projects."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_principal, guardrails
from app.core import projects
from app.core.errors import NotFoundError
from app.core.guardrails import Guardrails
from app.core.rbac import Principal
from app.models.schemas import ProjectCreate, ProjectList, ProjectOut

router = APIRouter()


@router.get("/projects", response_model=ProjectList, summary="List projects")
async def list_projects(
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> ProjectList:
    guard.authorize(principal, "project:read", resource="project")
    items = projects.list_projects()
    return ProjectList(items=[ProjectOut(**p.model_dump()) for p in items], total=len(items))


@router.post("/projects", response_model=ProjectOut, status_code=201, summary="Create a project")
async def create_project(
    request: ProjectCreate,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> ProjectOut:
    guard.authorize(principal, "project:create", resource="project")
    project = projects.create(
        name=request.name,
        description=request.description,
        target=request.target,
        pdb_id=request.pdb_id,
        objectives=request.objectives,
        created_by=principal.id,
        project_id=request.id,
    )
    return ProjectOut(**project.model_dump())


@router.get("/projects/{project_id}", response_model=ProjectOut, summary="Get a project")
async def get_project(
    project_id: str,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> ProjectOut:
    guard.authorize(principal, "project:read", resource=f"project:{project_id}")
    p = projects.get(project_id)
    if p is None:
        raise NotFoundError(f"project '{project_id}' not found", project_id=project_id)
    return ProjectOut(**p.model_dump())
