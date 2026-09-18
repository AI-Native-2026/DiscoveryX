"""Async task entrypoints executed by the worker.

``run_dmta_task`` is the function ARQ invokes. It owns the task lifecycle
(running → succeeded / failed / blocked) and streams progress into Redis.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import GuardrailViolation
from app.core.logging import get_logger, set_trace_id
from app.models.schemas import TaskStatus, _now
from app.tasks import queue

logger = get_logger("discoveryx.workflow")


async def _progress(task_id: str, stage: str, round_no: int, pct: float, message: str, **extra: Any) -> None:
    state = await queue.load_state(task_id)
    if state is None:
        return
    state.stage = stage
    state.round = round_no
    state.progress = max(0.0, min(1.0, pct))
    state.updated_at = _now()
    state.events.append({"ts": _now(), "stage": stage, "round": round_no, "message": message, **extra})
    state.events = state.events[-200:]
    await queue.save_state(state)


async def run_dmta_task(ctx: dict[str, Any], task_id: str, payload: dict[str, Any], trace_id: str) -> str:
    """Execute one DMTA workflow task. Returns the final status."""
    set_trace_id(trace_id)
    logger.info("task %s started", task_id)

    state = await queue.load_state(task_id)
    if state is None:
        state = queue.new_task_state(task_id, int(payload.get("rounds", 3)), trace_id)
    state.status = TaskStatus.RUNNING
    state.trace_id = trace_id
    await queue.save_state(state)

    # Imported lazily so the worker can start without heavy optional deps.
    from app.core.agent_graph import run_dmta_workflow

    async def progress(stage: str, round_no: int, pct: float, message: str, **extra: Any) -> None:
        await _progress(task_id, stage, round_no, pct, message, **extra)

    try:
        report = await run_dmta_workflow(task_id, payload, trace_id, progress)
        state = await queue.load_state(task_id) or state
        state.status = TaskStatus.SUCCEEDED
        state.stage = "done"
        state.progress = 1.0
        state.result = report.model_dump()
        state.token_usage = report.token_usage
        state.updated_at = _now()
        await queue.save_state(state)

        # Raise a human-in-the-loop approval for the run's recommendation.
        try:
            from app.core import approvals

            top = report.top_candidates[:5]
            if top:
                approvals.create(
                    task_id=task_id,
                    kind="advance_candidates",
                    title=f"批准将 {len(top)} 个候选化合物推进到合成与活性验证",
                    detail=report.decision or "DMTA 运行已完成，请复核候选化合物。",
                    payload={
                        "decision": report.decision,
                        "candidates": [
                            {"id": c.id, "smiles": c.smiles, "pIC50": c.pIC50, "mpo": c.mpo}
                            for c in top
                        ],
                    },
                    requested_by=payload.get("_principal", {}).get("id", "system"),
                )
        except Exception as exc:  # noqa: BLE001 - never fail the run on approval bookkeeping
            logger.warning("approval request failed: %s", exc)

        logger.info("task %s succeeded", task_id)
        return TaskStatus.SUCCEEDED.value

    except GuardrailViolation as exc:
        # Security blocks are deterministic: never retried.
        state = await queue.load_state(task_id) or state
        state.status = TaskStatus.BLOCKED
        state.stage = "blocked"
        state.error = exc.message
        state.updated_at = _now()
        state.events.append({"ts": _now(), "stage": "blocked", "message": exc.message, "guardrail": exc.guardrail})
        await queue.save_state(state)
        logger.warning("task %s blocked by guardrail: %s", task_id, exc.message)
        return TaskStatus.BLOCKED.value

    except Exception as exc:  # noqa: BLE001 - infrastructure / unexpected failure
        attempt = int(ctx.get("job_try", 1) or 1)
        max_tries = int(ctx.get("max_tries", 1) or 1)
        state = await queue.load_state(task_id) or state
        state.attempts = attempt
        state.updated_at = _now()

        if attempt < max_tries:
            # transient failure: record and let the worker retry with backoff
            state.status = TaskStatus.QUEUED
            state.stage = "retrying"
            state.error = f"attempt {attempt}/{max_tries}: {type(exc).__name__}: {exc}"
            state.events.append(
                {"ts": _now(), "stage": "retrying", "message": state.error, "attempt": attempt}
            )
            await queue.save_state(state)
            logger.warning("task %s attempt %d/%d failed, retrying: %s", task_id, attempt, max_tries, exc)
            raise

        state.status = TaskStatus.FAILED
        state.stage = "failed"
        state.error = f"{type(exc).__name__}: {exc}"
        state.events.append({"ts": _now(), "stage": "failed", "message": state.error, "attempt": attempt})
        await queue.save_state(state)
        logger.exception("task %s failed after %d attempt(s)", task_id, attempt)
        return TaskStatus.FAILED.value
