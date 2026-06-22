"""Hangar application factory (T019).

Wires the fail-closed startup gate (Constitution III), structured logging, the forward-
auth middleware, the API surface, the sync scheduler lifespan, and (in production) the
built SPA as static assets. ``/health`` is also exposed at the root for the container
healthcheck.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hangar.api import api_router
from hangar.auth.forward_auth import ForwardAuthMiddleware
from hangar.config import Settings, get_settings, validate_startup
from hangar.persistence.db import create_all, get_sessionmaker
from hangar.services import webhooks
from hangar.services.sync import SyncService

log = structlog.get_logger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # Fail-closed gate — raises StartupError if access mode unset / unsafe bind (FR-029/030).
    warnings = validate_startup(settings)
    for w in warnings:
        log.warning("startup.warning", message=w)

    await create_all()
    sync = SyncService()
    await sync.ensure_seed()
    app.state.sync = sync
    if not _is_testing():
        sync.start()
    mode = settings.access_mode
    log.info(
        "hangar.started",
        access_mode=mode.value if mode else None,
        host=settings.host,
    )
    try:
        yield
    finally:
        sync.shutdown()
        log.info("hangar.stopped")


def _is_testing() -> bool:
    return "pytest" in sys.modules


def create_app() -> FastAPI:
    _configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="Hangar Fleet Control Plane API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Forward-auth is the outermost security boundary (Constitution III).
    app.add_middleware(ForwardAuthMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/health", tags=["system"])
    async def root_health() -> dict:
        return {"status": "ok"}

    @app.post("/api/v1/webhooks/{connection_id}")
    async def receive_webhook(connection_id: str, request: Request) -> JSONResponse:
        # The webhook is authenticated by its HMAC signature, not the proxy identity —
        # providers POST directly (not through the forward-auth proxy). It is therefore
        # exempted from ForwardAuthMiddleware (see _PUBLIC_PATHS) and MUST verify the
        # signature here, failing closed when no secret is configured (FR-033).
        secret = _webhook_secret(connection_id)
        if not secret:
            return JSONResponse(
                {"accepted": False, "reason": "webhooks not configured (HANGAR_WEBHOOK_SECRET unset)"},
                status_code=503,
            )
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256")
        if not webhooks.verify_signature(secret, body, signature):
            return JSONResponse({"accepted": False, "reason": "invalid signature"}, status_code=401)

        import json

        event = request.headers.get("X-GitHub-Event", "")
        payload = json.loads(body or b"{}")
        async with get_sessionmaker()() as session:
            updated = await webhooks.apply_event(session, event, payload, connection_id)
        return JSONResponse({"accepted": True, "updated": updated})

    _mount_spa(app, settings)
    return app


def _mount_spa(app: FastAPI, settings: Settings) -> None:
    """Serve the built SPA at / in the single-stack deployment (Constitution V).

    Unknown non-API paths fall back to index.html so client-side routes (/scorecard,
    /repos/:id, …) resolve. No-op when HANGAR_STATIC_DIR is unset or missing.
    """
    import os

    static_dir = settings.static_dir
    if not static_dir or not os.path.isdir(static_dir):
        return

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    assets = os.path.join(static_dir, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index = os.path.join(static_dir, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        return FileResponse(safe_static_file(static_dir, full_path) or index)

    log.info("spa.mounted", static_dir=static_dir)


def safe_static_file(static_dir: str, full_path: str) -> str | None:
    """Resolve ``full_path`` to a real file confined within ``static_dir``.

    Returns the absolute path only when it is an existing file at or below
    ``static_dir``; returns None for traversal attempts (``..`` segments, which
    Starlette's path converter passes through un-normalized) or non-files, so the
    caller falls back to index.html. Prevents arbitrary-file-read via the SPA route.
    """
    import os

    root = os.path.realpath(static_dir)
    candidate = os.path.realpath(os.path.join(static_dir, full_path))
    contained = candidate == root or candidate.startswith(root + os.sep)
    if full_path and contained and os.path.isfile(candidate):
        return candidate
    return None


def _webhook_secret(connection_id: str) -> str | None:
    # The webhook HMAC secret is supplied via HANGAR_WEBHOOK_SECRET (shared across the
    # App's webhook deliveries). When unset, inbound webhooks are refused (fail-closed)
    # rather than accepted unsigned.
    return get_settings().webhook_secret


app = create_app()
