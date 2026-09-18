"""ARQ worker settings.

Run with:  arq app.tasks.worker.WorkerSettings
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger, setup_logging
from app.tasks.queue import redis_settings
from app.tasks.workflow import run_dmta_task

logger = get_logger("discoveryx.worker")


async def on_startup(ctx: dict[str, Any]) -> None:
    from app.tasks.queue import clear_stale_in_progress
    from config.settings import get_settings

    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json, secrets=[settings.deepseek_api_key or ""])
    settings.ensure_dirs()
    await clear_stale_in_progress(ctx["redis"])
    logger.info("worker started", extra={"extra_fields": {"redis": settings.redis_url}})


async def on_shutdown(ctx: dict[str, Any]) -> None:
    from app.tasks.queue import close_pool

    await close_pool()
    logger.info("worker stopped")


class WorkerSettings:
    functions = [run_dmta_task]
    redis_settings = redis_settings()
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 2
    job_timeout = 60 * 30
    keep_result = 3600
    # Infrastructure failures are retried; guardrail blocks never raise, so they
    # are never retried (deterministic security).
    max_tries = 2
    retry_jobs = True
    health_check_interval = 30
