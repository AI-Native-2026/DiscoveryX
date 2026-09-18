"""Dataset catalog API — directory-based datasets, files, upload and RAG indexing."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.api.deps import get_principal, guardrails
from app.core.datasets import DatasetRegistry
from app.core.errors import NotFoundError, ValidationError
from app.core.guardrails import Guardrails
from app.core.logging import get_logger
from app.core.rbac import Principal
from app.models.schemas import DatasetCreate, DatasetFileList, DatasetInfo, DatasetList

logger = get_logger("discoveryx.api.datasets")

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB per file


def _safe_relpath(name: str) -> str:
    """Reject path traversal; keep a flat relative path."""
    p = Path(name)
    if p.is_absolute() or ".." in p.parts:
        raise ValidationError(f"invalid file name '{name}'")
    return "/".join(part for part in p.parts if part not in ("", "."))


@router.get("/datasets", response_model=DatasetList, summary="List dataset directories")
async def list_datasets(
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> DatasetList:
    guard.authorize(principal, "dataset:read", resource="dataset")
    items = DatasetRegistry().list()
    visible = guard.filter_datasets(items, principal)
    return DatasetList(items=visible, total=len(visible))


@router.post("/datasets", response_model=DatasetInfo, status_code=201, summary="Register a dataset directory")
async def create_dataset(
    request: DatasetCreate,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> DatasetInfo:
    """Create a dataset directory (e.g. ``AAA/``) with metadata.

    Files are added by uploading/copying them into the directory; use the index
    endpoint to build the RAG index from its documents.
    """
    guard.authorize(principal, "dataset:import", resource="dataset")
    guard.authorize_level(principal, request.sensitivity.value, resource=f"dataset:{request.id}")
    reg = DatasetRegistry()
    reg.ensure_dir(
        request.id,
        meta={
            "name": request.name,
            "data_type": request.data_type.value,
            "source": request.source,
            "sensitivity": request.sensitivity.value,
            "purpose": request.purpose.value,
            "description": request.description,
            "owner": principal.id,
        },
    )
    info = reg.get(request.id)
    if info is None:  # pragma: no cover - defensive
        raise NotFoundError(f"failed to create dataset '{request.id}'")
    return info


@router.get("/datasets/{dataset_id}", response_model=DatasetInfo, summary="Get a dataset")
async def get_dataset(
    dataset_id: str,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> DatasetInfo:
    guard.authorize(principal, "dataset:read", resource=f"dataset:{dataset_id}")
    info = DatasetRegistry().get(dataset_id)
    if info is None:
        raise NotFoundError(f"dataset '{dataset_id}' not found", dataset_id=dataset_id)
    guard.authorize_level(principal, info.sensitivity.value, resource=f"dataset:{dataset_id}")
    return info


@router.post("/datasets/{dataset_id}/upload", summary="Upload files into a dataset directory")
async def upload_files(
    dataset_id: str,
    files: list[UploadFile] = File(..., description="Files to store in the dataset directory"),
    subdir: str = Form(default="", description="Optional sub-directory inside the dataset"),
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> dict:
    """Upload PDFs, Excel sheets, CSVs … into ``data/datasets/<dataset_id>/``."""
    guard.authorize(principal, "dataset:import", resource=f"dataset:{dataset_id}")
    reg = DatasetRegistry()
    info = reg.get(dataset_id)
    if info is None:
        raise NotFoundError(f"dataset '{dataset_id}' not found", dataset_id=dataset_id)
    guard.authorize_level(principal, info.sensitivity.value, resource=f"dataset:{dataset_id}")

    target_dir = reg.root / dataset_id
    if subdir:
        target_dir = target_dir / _safe_relpath(subdir)
    target_dir.mkdir(parents=True, exist_ok=True)

    saved: list[dict] = []
    for upload in files:
        rel = _safe_relpath(upload.filename or "unnamed")
        dest = target_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValidationError(f"file '{rel}' exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        dest.write_bytes(data)
        saved.append({"file": rel, "bytes": len(data)})

    logger.info("uploaded %d file(s) into dataset %s", len(saved), dataset_id)
    return {"dataset_id": dataset_id, "uploaded": len(saved), "files": saved}


@router.delete("/datasets/{dataset_id}", summary="Delete a dataset directory")
async def delete_dataset(
    dataset_id: str,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> dict:
    """Remove a dataset directory, its RAG collection and its index state."""
    guard.authorize(principal, "dataset:delete", resource=f"dataset:{dataset_id}")
    reg = DatasetRegistry()
    info = reg.get(dataset_id)
    if info is None:
        raise NotFoundError(f"dataset '{dataset_id}' not found", dataset_id=dataset_id)
    guard.authorize_level(principal, info.sensitivity.value, resource=f"dataset:{dataset_id}")
    result = reg.delete(dataset_id)
    logger.info("dataset deleted", extra={"extra_fields": {"dataset_id": dataset_id, "actor": principal.id}})
    return result


@router.get("/datasets/{dataset_id}/files", response_model=DatasetFileList, summary="List files in a dataset")
async def list_dataset_files(
    dataset_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> DatasetFileList:
    guard.authorize(principal, "dataset:read", resource=f"dataset:{dataset_id}")
    reg = DatasetRegistry()
    info = reg.get(dataset_id)
    if info is None:
        raise NotFoundError(f"dataset '{dataset_id}' not found", dataset_id=dataset_id)
    guard.authorize_level(principal, info.sensitivity.value, resource=f"dataset:{dataset_id}")
    files = reg.files(dataset_id, limit=limit)
    return DatasetFileList(
        dataset_id=dataset_id,
        items=files,  # type: ignore[arg-type]
        total=info.n_files,
        file_types=info.file_types,
    )


@router.post("/datasets/{dataset_id}/index", summary="Index a dataset's documents into the knowledge base")
async def index_dataset(
    dataset_id: str,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> dict:
    """Extract text from the dataset directory and index it into ChromaDB."""
    guard.authorize(principal, "dataset:index", resource=f"dataset:{dataset_id}")
    reg = DatasetRegistry()
    info = reg.get(dataset_id)
    if info is None:
        raise NotFoundError(f"dataset '{dataset_id}' not found", dataset_id=dataset_id)
    guard.authorize_level(principal, info.sensitivity.value, resource=f"dataset:{dataset_id}")

    from app.core.rag_engine import RAGEngine

    collection = f"kb_{info.sensitivity.value}_{dataset_id}"
    engine = RAGEngine()

    docs = []
    for doc in reg.documents(dataset_id):
        docs.append(
            {
                "id": doc["id"],
                "text": doc["text"],
                "title": doc["metadata"].get("file", dataset_id),
                "journal": info.source,
                "year": "",
                "file": doc["metadata"].get("file", ""),
            }
        )

    chunks = engine.index_documents(
        docs,
        collection=collection,
        sensitivity=info.sensitivity.value,
        source=f"dataset:{dataset_id}",
    )
    reg.mark_indexed(dataset_id, chunks=chunks, collection=collection)
    logger.info("indexed dataset %s -> %d chunks", dataset_id, chunks)
    return {
        "dataset_id": dataset_id,
        "documents": len(docs),
        "chunks": chunks,
        "collection": collection,
        "sensitivity": info.sensitivity.value,
        "task_id": f"index-{uuid.uuid4().hex[:8]}",
    }
