"""Copilot API — a real, guardrailed research assistant."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_principal
from app.core.copilot import get_copilot
from app.core.rbac import Principal
from app.models.schemas import CopilotReply, CopilotRequest

router = APIRouter()


@router.post("/copilot/chat", response_model=CopilotReply, summary="Ask the Copilot")
async def copilot_chat(
    request: CopilotRequest,
    principal: Principal = Depends(get_principal),
) -> CopilotReply:
    """Answer a question using the current run context and the PMC knowledge base.

    RBAC-checked (`copilot:chat`), DLP-scanned, metered and audited.
    """
    copilot = get_copilot()
    return await copilot.chat(
        request.message,
        principal,
        task_id=request.task_id,
        history=request.history,
    )
