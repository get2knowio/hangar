"""System endpoints: /health (unauthenticated) and /me (FR-038, Constitution VI)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.api.deps import session_dep, settings_dep
from hangar.config import Settings
from hangar.persistence import repositories as repo_store
from hangar.services.sync import is_stale

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(
    session: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> dict:
    connections = await repo_store.list_connections(session)
    conn_state = [
        {
            "id": c.id,
            "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
            "stale": is_stale(c.last_sync_at),
        }
        for c in connections
    ]
    degraded = any(s["stale"] for s in conn_state)
    return {
        "status": "degraded" if degraded else "ok",
        "access_mode": settings.access_mode.value if settings.access_mode else None,
        "connections": conn_state,
    }


@router.get("/me")
async def me(request: Request, settings: Settings = Depends(settings_dep)) -> dict:
    actor = getattr(request.state, "actor", None) or settings.operator
    return {
        "actor": actor,
        "access_mode": settings.access_mode.value if settings.access_mode else "disabled",
        "user_header": settings.forward_auth_user_header,
    }
