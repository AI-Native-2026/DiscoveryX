"""RAG API — PMC-grounded retrieval-augmented answering."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_principal, guardrails
from app.core.guardrails import Guardrails
from app.core.rbac import Principal
from app.models.schemas import RAGQuery, RAGResult

router = APIRouter()


@router.post("/rag/query", response_model=RAGResult, summary="Query the knowledge base")
async def rag_query(
    request: RAGQuery,
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> RAGResult:
    guard.authorize(principal, "rag:query", resource="rag")
    from app.core.rag_engine import RAGEngine

    engine = RAGEngine()
    return await engine.query(
        request.query,
        principal,
        top_k=request.top_k,
        collections=request.collections,
        guard=guard,
    )


@router.get("/rag/status", summary="Knowledge base status")
async def rag_status(
    principal: Principal = Depends(get_principal),
    guard: Guardrails = Depends(guardrails),
) -> dict:
    guard.authorize(principal, "rag:query", resource="rag")
    from app.core.rag_engine import RAGEngine

    return RAGEngine().status()
