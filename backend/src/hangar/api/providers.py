"""Providers & access endpoints (FR-021–FR-032)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.api.deps import session_dep, settings_dep
from hangar.config import Settings
from hangar.domain.models import ProviderConnection
from hangar.persistence import repositories as repo_store
from hangar.providers.base import provider_name
from hangar.services import connections as conn_service
from hangar.services.sync import format_relative

router = APIRouter(tags=["providers"])


async def _connection_card(
    session: AsyncSession, conn: ProviderConnection, repo_count: int
) -> dict:
    return {
        "id": conn.id,
        "label": conn.label,
        "type": provider_name(conn.provider_type),
        "scope": conn.scope,
        "auth_mode": conn.auth_mode,
        "repos": repo_count,
        "writes": conn.writes,
        "write_label": "Read + write" if conn.writes else "Read-only",
        "remediation": "API + PR + deep-link" if conn.writes else "Deep-link only",
        "synced": format_relative(conn.last_sync_at),
    }


@router.get("/providers")
async def list_providers(
    session: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> dict:
    conns = await repo_store.list_connections(session)
    # One query for all repo counts grouped by connection, instead of N per-card queries.
    counts = await repo_store.repo_counts_by_connection(session)
    cards = [await _connection_card(session, c, counts.get(c.id, 0)) for c in conns]
    return {
        "access": {
            "mode": settings.access_mode.value if settings.access_mode else "disabled",
            "user_header": settings.forward_auth_user_header,
            "allowed_user": settings.forward_auth_allowed_user,
            "fail_closed": True,
        },
        "connections": cards,
    }


class NewConnection(BaseModel):
    provider_type: str
    label: str
    scope: str
    auth_mode: str | None = None
    # For a GitHub App connection: the App private-key PEM. For PAT/Gitea: the token.
    credential: str | None = None
    # GitHub App identity (omit for a PAT/token connection).
    app_id: str | None = None
    installation_id: int | None = None
    # Least-privilege default: a connection is read-only unless the operator declares
    # the credential is writable (FR-026/FR-018).
    writable: bool = False


@router.post("/providers", status_code=201)
async def add_provider(
    body: NewConnection, session: AsyncSession = Depends(session_dep)
) -> dict:
    conn = await conn_service.add_connection(
        session,
        provider_type=body.provider_type,
        label=body.label,
        scope=body.scope,
        auth_mode=body.auth_mode or "",
        credential=body.credential,
        writable=body.writable,
        app_id=body.app_id,
        installation_id=body.installation_id,
    )
    repos = await repo_store.list_repos(session, conn.id)
    return await _connection_card(session, conn, len(repos))


@router.delete("/providers/{connection_id}", status_code=204)
async def remove_provider(
    connection_id: str, session: AsyncSession = Depends(session_dep)
) -> Response:
    await conn_service.remove_connection(session, connection_id)
    return Response(status_code=204)


@router.get("/providers/audit")
async def audit_log(
    limit: int = Query(50), session: AsyncSession = Depends(session_dep)
) -> list[dict]:
    entries = await repo_store.list_audit(session, limit)
    return [
        {
            "timestamp": format_relative(e.timestamp),
            "repo_id": e.repo_id,
            "check_label": e.check_label,
            "connection_label": e.connection_label,
            "actor": e.actor,
            "result": e.result,
            "pr_url": e.pr_url,
        }
        for e in entries
    ]
