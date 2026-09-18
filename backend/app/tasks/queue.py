"""Async task queue (Redis-backed, asyncio-native).

Tasks are enqueued by the API and executed by a separate worker process. Task
state lives in Redis so the API can report progress without touching the worker.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.logging import get_logger
from app.models.schemas import TaskState, TaskStatus

logger = get_logger("discoveryx.tasks")

TASK_KEY = "dx:task:{task_id}"
TASK_INDEX = "dx:tasks:index"
DMTA_FUNCTION = "run_dmta_task"


def redis_settings() -> RedisSettings:
    from config.settings import get_settings

    # ARQ defaults to a 1s connection timeout. The worker shares the CPU with
    # chemistry and ML workloads, so give connections generous headroom: a slow
    # handshake retries instead of aborting the process.
    return replace(
        RedisSettings.from_dsn(get_settings().redis_url),
        conn_timeout=15,
        conn_retries=10,
        conn_retry_delay=1,
        max_connections=20,
        retry_on_timeout=True,
    )


IN_PROGRESS_PREFIX = "arq:in-progress:"


async def clear_stale_in_progress(pool: ArqRedis) -> int:
    """Drop leftover ``arq:in-progress:*`` keys at worker startup.

    ARQ treats an existing in-progress key as "another worker owns this job" and
    skips it until the key expires (``job_timeout + 10s``). At startup this
    process owns nothing, so clearing the keys lets queued work begin
    immediately instead of waiting out the TTL.
    """
    stale = [k async for k in pool.scan_iter(match=f"{IN_PROGRESS_PREFIX}*")]
    if stale:
        await pool.delete(*stale)
        logger.warning("cleared %d stale in-progress key(s)", len(stale))
    return len(stale)


_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


# ------------------------------------------------------------------ state
def _key(task_id: str) -> str:
    return TASK_KEY.format(task_id=task_id)


async def save_state(state: TaskState) -> None:
    from config.settings import get_settings

    pool = await get_pool()
    await pool.set(_key(state.task_id), state.model_dump_json(), ex=get_settings().task_ttl_seconds)


async def load_state(task_id: str) -> TaskState | None:
    pool = await get_pool()
    raw = await pool.get(_key(task_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return TaskState.model_validate_json(raw)


async def append_event(task_id: str, stage: str, message: str, **fields: Any) -> None:
    """Append a progress event and persist the state."""
    from app.models.schemas import _now

    state = await load_state(task_id)
    if state is None:
        return
    state.stage = stage
    state.updated_at = _now()
    state.events.append({"ts": _now(), "stage": stage, "message": message, **fields})
    state.events = state.events[-200:]
    await save_state(state)


# ------------------------------------------------------------------ enqueue
async def index_task(task_id: str) -> None:
    pool = await get_pool()
    await pool.lpush(TASK_INDEX, task_id)
    await pool.ltrim(TASK_INDEX, 0, 199)


async def list_task_ids(limit: int = 50) -> list[str]:
    pool = await get_pool()
    raw = await pool.lrange(TASK_INDEX, 0, max(0, limit - 1))
    return [x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in raw]


async def enqueue_dmta_task(task_id: str, payload: dict[str, Any], trace_id: str) -> None:
    pool = await get_pool()
    job = await pool.enqueue_job(DMTA_FUNCTION, task_id, payload, trace_id, _job_id=task_id)
    logger.info("enqueued %s job=%s", DMTA_FUNCTION, getattr(job, "job_id", task_id))


def new_task_state(
    task_id: str,
    rounds: int,
    trace_id: str,
    *,
    project: str | None = None,
    dataset_id: str | None = None,
    target: str | None = None,
    objectives: list[str] | None = None,
) -> TaskState:
    return TaskState(
        task_id=task_id,
        project=project,
        dataset_id=dataset_id,
        target=target,
        objectives=objectives or [],
        status=TaskStatus.QUEUED,
        stage="queued",
        round=0,
        rounds=rounds,
        progress=0.0,
        trace_id=trace_id,
        events=[{"ts": None, "stage": "queued", "message": "task queued"}],
    )
