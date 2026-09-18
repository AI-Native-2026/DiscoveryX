"""Copilot — a real, guardrailed research assistant.

The Copilot answers questions about the current run and the scientific
literature. It grounds answers in the RAG knowledge base (PMC) and, when a task
is in scope, in that task's live state. Every call is RBAC-checked, DLP-scanned
and metered.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.guardrails import Guardrails, get_guardrails
from app.core.llm_factory import ChatMessage, LLMFactory, TokenLedger
from app.core.logging import get_logger
from app.core.rbac import Principal
from app.models.schemas import CopilotReply, CopilotStep, TokenUsage

logger = get_logger("discoveryx.copilot")

SYSTEM_PROMPT = (
    "You are DiscoveryX Copilot, an assistant for medicinal chemists and discovery scientists. "
    "Answer concisely and technically. Ground your answer in the provided run context and "
    "literature sources; cite sources inline as [n]. If the context is insufficient, say so "
    "explicitly and suggest what data would be needed. Never invent assay numbers."
)


class Copilot:
    def __init__(self, guard: Guardrails | None = None) -> None:
        self.guard = guard or get_guardrails()

    async def _task_context(self, task_id: str) -> tuple[str, list[CopilotStep], str | None]:
        """Return (context, steps, dataset_id) for the run in scope."""
        steps: list[CopilotStep] = []
        try:
            from app.tasks import queue

            state = await queue.load_state(task_id)
        except Exception as exc:  # noqa: BLE001 - redis may be unavailable
            logger.warning("copilot task context failed: %s", exc)
            return "", steps, None
        if state is None:
            return "", steps, None

        steps.append(CopilotStep(tool="task_context", detail=f"{task_id} · {state.status}"))
        lines = [
            f"Run {state.task_id}: target={state.target or 'n/a'}, "
            f"dataset={state.dataset_id or 'n/a'}, status={state.status}, stage={state.stage}, "
            f"round={state.round}/{state.rounds}, progress={round(state.progress * 100)}%",
        ]
        if state.objectives:
            lines.append(f"Objectives: {', '.join(state.objectives)}")
        report = state.result or {}
        if report.get("decision"):
            lines.append(f"Decision: {report['decision']}")
        for r in (report.get("rounds") or []):
            lines.append(f"- R{r.get('round')}: {r.get('summary')}")
        for c in (report.get("top_candidates") or [])[:5]:
            lines.append(
                f"- candidate #{c.get('id')} SMILES={c.get('smiles')} pIC50={c.get('pIC50')} "
                f"BBB={c.get('bbb')} hepatotoxic={c.get('hepatotoxic')} SA={c.get('sa_score')} "
                f"route_steps={c.get('route_steps')} MPO={c.get('mpo')}"
            )
        for e in (report.get("evidence") or [])[:6]:
            lines.append(f"- evidence {e.get('type')}:{e.get('id')} {e.get('title', '')}")
        if state.error:
            lines.append(f"Error/guardrail: {state.error}")
        return "\n".join(lines), steps, state.dataset_id

    async def _rag_context(
        self,
        message: str,
        principal: Principal,
        *,
        dataset_id: str | None = None,
        ledger: Any = None,
    ) -> tuple[str, list[Any], list[CopilotStep]]:
        """Retrieve literature, scoped to the run's dataset when one is in scope.

        A run must not be answered with literature that belongs to a different
        dataset: a MetAP2 run citing BACE1 papers would be misleading. When the
        run's dataset has no indexed collection we return no sources rather than
        pulling unrelated ones.
        """
        steps: list[CopilotStep] = []
        try:
            from app.core.rag_engine import RAGEngine

            engine = RAGEngine()
            if engine.status()["total_chunks"] == 0:
                steps.append(CopilotStep(tool="rag_search", detail="knowledge base empty", status="skip"))
                return "", [], steps

            collections: list[str] | None = None
            if dataset_id:
                from app.core.datasets import DatasetRegistry

                state = DatasetRegistry().index_state(dataset_id)
                collection = state.get("collection")
                if not state.get("indexed") or not collection:
                    steps.append(
                        CopilotStep(
                            tool="rag_search",
                            detail=f"dataset '{dataset_id}' has no indexed literature",
                            status="skip",
                        )
                    )
                    return "", [], steps
                collections = [collection]

            result = await engine.query(
                message, principal, top_k=4, collections=collections, guard=self.guard, ledger=ledger
            )
            steps.append(
                CopilotStep(tool="rag_search", detail=f"{result.used_chunks} chunks used", status="ok")
            )
            if not result.citations:
                return "", [], steps
            blocks = []
            for i, c in enumerate(result.citations, 1):
                blocks.append(f"[{i}] {c.id} - {c.title} ({c.source})\n{c.snippet}")
            return "\n\n".join(blocks), result.citations, steps
        except Exception as exc:  # noqa: BLE001
            logger.warning("copilot rag failed: %s", exc)
            steps.append(CopilotStep(tool="rag_search", detail=str(exc)[:80], status="error"))
            return "", [], steps

    async def chat(
        self,
        message: str,
        principal: Principal,
        *,
        task_id: str | None = None,
        history: Sequence[Any] | None = None,
    ) -> CopilotReply:
        ledger = TokenLedger()
        steps: list[CopilotStep] = []

        # 1) RBAC + DLP
        self.guard.authorize(principal, "copilot:chat", resource="copilot")
        safe_message = self.guard.check_outbound(message, principal, action="copilot:chat", resource="copilot")
        steps.append(CopilotStep(tool="guardrails", detail="rbac ok · dlp ok"))

        # 2) context — literature is scoped to the run's dataset
        task_ctx = ""
        dataset_id: str | None = None
        if task_id:
            task_ctx, task_steps, dataset_id = await self._task_context(task_id)
            steps.extend(task_steps)
        rag_ctx, citations, rag_steps = await self._rag_context(
            safe_message, principal, dataset_id=dataset_id, ledger=ledger
        )
        steps.extend(rag_steps)

        # 3) prompt
        parts: list[str] = []
        if task_ctx:
            parts.append(f"## Current run\n{task_ctx}")
        if rag_ctx:
            scope = f" (dataset: {dataset_id})" if dataset_id else ""
            parts.append(f"## Literature sources{scope}\n{rag_ctx}")
        elif dataset_id:
            parts.append(
                f"## Literature sources\nNo indexed literature exists for dataset "
                f"'{dataset_id}'. Answer from the run context only and say that no "
                f"dataset-specific literature is indexed."
            )
        context = "\n\n".join(parts) or "(no additional context available)"

        messages: list[ChatMessage] = [ChatMessage.system(SYSTEM_PROMPT)]
        for h in (history or [])[-6:]:
            role = getattr(h, "role", None) or (h.get("role") if isinstance(h, dict) else "user")
            content = getattr(h, "content", None) or (h.get("content") if isinstance(h, dict) else "")
            if content:
                messages.append(ChatMessage(role=role, content=str(content)))
        messages.append(ChatMessage.user(f"{context}\n\n## Question\n{safe_message}"))

        try:
            llm = LLMFactory(ledger)
            result = llm.complete(
                messages,
                model="reasoner" if len(safe_message) > 120 else None,
                principal=principal,
                guard=self.guard,
                purpose="copilot",
            )
            steps.append(CopilotStep(tool="llm", detail=f"{result.usage.total_tokens} tokens"))
            return CopilotReply(
                answer=result.content.strip(),
                citations=citations,
                steps=steps,
                token_usage=ledger.snapshot(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("copilot llm failed: %s", exc)
            return CopilotReply(
                answer=f"无法调用模型（{type(exc).__name__}）。已收集到的上下文：\n\n{context[:800]}",
                citations=citations,
                steps=steps,
                token_usage=TokenUsage(),
            )


_copilot: Copilot | None = None


def get_copilot() -> Copilot:
    global _copilot
    if _copilot is None:
        _copilot = Copilot()
    return _copilot


def reset_copilot() -> None:
    global _copilot
    _copilot = None
