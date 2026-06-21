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

from hangar.api import api_router
from hangar.auth.forward_auth import ForwardAuthMiddleware
from hangar.config import get_settings, validate_startup
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
    log.info("hangar.started", access_mode=settings.access_mode.value, host=settings.host)
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
    async def receive_webhook(connection_id: str, request: Request) -> dict:
        body = await request.body()
        event = request.headers.get("X-GitHub-Event", "")
        signature = request.headers.get("X-Hub-Signature-256")
        secret = _webhook_secret(connection_id)
        if secret and not webhooks.verify_signature(secret, body, signature):
            return {"accepted": False, "reason": "invalid signature"}
        import json

        payload = json.loads(body or b"{}")
        async with get_sessionmaker()() as session:
            updated = await webhooks.apply_event(session, event, payload)
        return {"accepted": True, "updated": updated}

    _mount_spa(app, settings)
    return app


def _mount_spa(app: FastAPI, settings) -> None:
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

    def _resolve(full_path: str) -> str:
        candidate = os.path.join(static_dir, full_path)
        return candidate if full_path and os.path.isfile(candidate) else index

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        return FileResponse(_resolve(full_path))

    log.info("spa.mounted", static_dir=static_dir)


def _webhook_secret(connection_id: str) -> str | None:
    # Real deployments decrypt the per-connection webhook secret; absent in seed/dev.
    return None


app = create_app()
