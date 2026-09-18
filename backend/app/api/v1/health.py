"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import HealthResponse

router = APIRouter()


async def _check_redis() -> str:
    try:
        from app.tasks.queue import get_pool

        pool = await get_pool()
        await pool.ping()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {type(exc).__name__}"


async def _check_llm() -> str:
    from config.settings import get_settings

    return "configured" if get_settings().has_llm() else "not-configured"


def _check_chroma() -> str:
    from config.settings import get_settings

    d = get_settings().chroma_dir
    return "ok" if d.exists() else "not-initialised"


@router.get("/health", response_model=HealthResponse, summary="Liveness / readiness")
async def health() -> HealthResponse:
    from config.settings import get_settings

    s = get_settings()
    return HealthResponse(
        status="ok",
        app=s.app_name,
        version=s.app_version,
        environment=s.environment,
        components={
            "redis": await _check_redis(),
            "llm": await _check_llm(),
            "chroma": _check_chroma(),
        },
    )


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
