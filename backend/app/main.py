from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.database.session import SessionFactory, close_database, create_schema
from app.security.bootstrap import seed_security
from app.services.runtime import Runtime

settings = get_settings()
configure_logging(settings.debug)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.database_auto_create:
        await create_schema()
    async with SessionFactory() as db:
        await seed_security(
            db,
            settings.bootstrap_admin_email,
            settings.bootstrap_admin_password,
            settings.bootstrap_admin_pin,
        )
    runtime = Runtime.build(settings)
    app.state.runtime = runtime
    await runtime.start()
    yield
    await runtime.stop()
    await close_database()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Simulation-first API for secure house control, automation, and telemetry.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
app.add_middleware(RequestContextMiddleware)
app.include_router(api_router, prefix=settings.api_prefix)


def error_payload(request: Request, code: str, message: Any, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, "context": {}},
            "request_id": getattr(request.state, "request_id", "unknown"),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return error_payload(request, f"http_{exc.status_code}", exc.detail, exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_payload(request, "validation_error", exc.errors(), 422)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready", tags=["system"])
async def ready(request: Request) -> JSONResponse:
    runtime: Runtime | None = getattr(request.app.state, "runtime", None)
    ready_state = runtime is not None and runtime.bus.connected
    return JSONResponse(
        status_code=200 if ready_state else 503,
        content={
            "status": "ready" if ready_state else "not_ready",
            "message_bus": bool(ready_state),
        },
    )
