"""FastAPI application factory.

Wires middleware (trace id), exception handling, CORS and the v1 routers, and
produces a complete OpenAPI schema (Swagger UI at ``/docs``).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import approvals, copilot, datasets, guardrails, health, projects, rag, tasks
from app.core.errors import DiscoveryXError, GuardrailViolation
from app.core.logging import get_logger, set_trace_id, setup_logging

logger = get_logger("discoveryx.api")

TRACE_HEADER = "X-Trace-Id"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from config.settings import get_settings

    settings = get_settings()
    settings.ensure_dirs()
    setup_logging(settings.log_level, settings.log_json, secrets=[settings.deepseek_api_key or ""])
    logger.info(
        "app starting",
        extra={"extra_fields": {"env": settings.environment, "version": settings.app_version}},
    )
    yield
    from app.tasks.queue import close_pool

    try:
        await close_pool()
    except Exception:  # pragma: no cover - redis may be unavailable
        pass
    logger.info("app stopped")


def create_app() -> FastAPI:
    from config.settings import get_settings

    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.app_version,
        description=(
            "DiscoveryX — an open, enterprise-grade AI platform for drug discovery. "
            "Agentic DMTA workflows, PMC-grounded RAG, real guardrails (RBAC/DLP/audit) "
            "and reproducible evaluation, exposed as an API-first service."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[TRACE_HEADER],
    )

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        trace_id = request.headers.get(TRACE_HEADER) or uuid.uuid4().hex[:16]
        set_trace_id(trace_id)
        response = await call_next(request)
        response.headers[TRACE_HEADER] = trace_id
        return response

    # ---- exception handlers ----
    @app.exception_handler(GuardrailViolation)
    async def _guardrail_handler(request: Request, exc: GuardrailViolation) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(DiscoveryXError)
    async def _domain_handler(request: Request, exc: DiscoveryXError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "message": "request validation failed", "details": exc.errors()},
        )

    # ---- routers ----
    prefix = settings.api_prefix
    app.include_router(health.router, prefix=prefix, tags=["health"])
    app.include_router(projects.router, prefix=prefix, tags=["projects"])
    app.include_router(tasks.router, prefix=prefix, tags=["tasks"])
    app.include_router(guardrails.router, prefix=prefix, tags=["guardrails"])
    app.include_router(rag.router, prefix=prefix, tags=["rag"])
    app.include_router(datasets.router, prefix=prefix, tags=["datasets"])
    app.include_router(copilot.router, prefix=prefix, tags=["copilot"])
    app.include_router(approvals.router, prefix=prefix, tags=["approvals"])

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "docs": "/docs", "version": settings.app_version}

    return app


app = create_app()
