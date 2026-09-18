"""Project registry.

A **project** is the unit a discovery team works on (a target, an objective, a
set of datasets and runs). Projects are stored on disk so the platform can host
several in parallel — the DMTA workflow, the workbench and the report are all
scoped to one project.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger

logger = get_logger("discoveryx.projects")

_lock = threading.Lock()

# No seed projects: the platform starts empty and projects are created by users.
DEFAULT_PROJECTS: list[dict[str, Any]] = []


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Project(BaseModel):
    id: str
    name: str
    description: str = ""
    target: str = "BACE1"
    pdb_id: str = "4WY1"
    objectives: list[str] = Field(default_factory=lambda: ["BBB", "hepatotoxicity"])
    created_by: str = "system"
    created_at: str = Field(default_factory=_now)


def _path() -> Path:
    from config.settings import get_settings

    p = get_settings().data_dir / "projects.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> list[Project]:
    p = _path()
    if not p.exists():
        rows = [Project(**d) for d in DEFAULT_PROJECTS]
        _save(rows)
        return rows
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover
        raw = DEFAULT_PROJECTS
    out: list[Project] = []
    for r in raw:
        try:
            out.append(Project.model_validate(r))
        except Exception:  # noqa: BLE001
            continue
    return out


def _save(rows: list[Project]) -> None:
    _path().write_text(
        json.dumps([r.model_dump(mode="json") for r in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_projects() -> list[Project]:
    return _load()


def get(project_id: str) -> Project | None:
    for p in _load():
        if p.id == project_id:
            return p
    return None


def create(
    *,
    name: str,
    description: str = "",
    target: str = "BACE1",
    pdb_id: str = "4WY1",
    objectives: list[str] | None = None,
    created_by: str = "system",
    project_id: str | None = None,
) -> Project:
    if project_id:
        pid = project_id
        if get(pid) is not None:
            raise ValidationError(f"project id '{pid}' already exists", project_id=pid)
    else:
        # derive a readable id and make it unique (so creation never fails on a name clash)
        base = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-") or f"proj-{uuid.uuid4().hex[:6]}"
        pid = base
        n = 2
        while get(pid) is not None:
            pid = f"{base}-{n}"
            n += 1

    project = Project(
        id=pid,
        name=name,
        description=description,
        target=target,
        pdb_id=pdb_id,
        objectives=objectives or ["BBB", "hepatotoxicity"],
        created_by=created_by,
    )
    with _lock:
        rows = _load()
        rows.append(project)
        _save(rows)
    logger.info("project created %s (%s)", project.id, project.name)
    return project


def update(project_id: str, **fields: Any) -> Project:
    with _lock:
        rows = _load()
        for p in rows:
            if p.id == project_id:
                for k, v in fields.items():
                    if v is not None and hasattr(p, k):
                        setattr(p, k, v)
                _save(rows)
                return p
    raise NotFoundError(f"project '{project_id}' not found", project_id=project_id)


def reset() -> None:
    with _lock:
        _save([Project(**d) for d in DEFAULT_PROJECTS])
