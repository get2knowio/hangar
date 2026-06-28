"""Providers & access endpoints (FR-021–FR-032)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.api.deps import session_dep, settings_dep
from hangar.config import Settings
from hangar.domain.models import ProviderConnection
from hangar.persistence import repositories as repo_store
from hangar.providers.base import provider_name
from hangar.providers.registry import provider_for
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
        # Raw provider type + credential presence let the add-connection form offer to
        # reuse an existing same-provider credential (so a PAT isn't re-pasted per org).
        "provider_type": conn.provider_type,
        "has_credential": conn.has_credential,
        "scope": conn.scope,
        "auth_mode": conn.auth_mode,
        "repos": repo_count,
        "writes": conn.writes,
        "write_label": "Read + write" if conn.writes else "Read-only",
        "remediation": "API + PR + deep-link" if conn.writes else "Deep-link only",
        "synced": format_relative(conn.last_sync_at),
        # None ⇒ watching all repos; a list ⇒ the operator's explicit selection.
        "repo_allowlist": conn.repo_allowlist,
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
    # Reuse another connection's stored credential instead of pasting one again (e.g. one
    # PAT across several orgs). Must reference an existing same-provider connection that
    # holds a credential; ignored when `credential` is provided directly.
    copy_credential_from: str | None = None
    # GitHub App identity (omit for a PAT/token connection).
    app_id: str | None = None
    installation_id: int | None = None
    # Optional per-connection inbound-webhook HMAC secret (else the global secret applies).
    webhook_secret: str | None = None
    # Optional owner (org/user) override; defaults to the label suffix.
    owner: str | None = None
    # Optional repo allowlist (repo names). Omit/null ⇒ watch every repo the credential
    # can see; a list scopes the connection's fleet to exactly those repos.
    repo_allowlist: list[str] | None = None
    # Least-privilege default: a connection is read-only unless the operator declares
    # the credential is writable (FR-026/FR-018).
    writable: bool = False


@router.post("/providers", status_code=201)
async def add_provider(
    body: NewConnection, session: AsyncSession = Depends(session_dep)
) -> dict:
    # Resolve a credential reused from another connection (so a PAT isn't re-pasted per
    # org). An explicitly-provided credential always wins.
    credential = body.credential
    if not credential and body.copy_credential_from:
        try:
            credential = await conn_service.credential_for_reuse(
                session, body.copy_credential_from, body.provider_type
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        conn = await conn_service.add_connection(
            session,
            provider_type=body.provider_type,
            label=body.label,
            scope=body.scope,
            auth_mode=body.auth_mode or "",
            credential=credential,
            writable=body.writable,
            app_id=body.app_id,
            installation_id=body.installation_id,
            webhook_secret=body.webhook_secret,
            owner=body.owner,
            repo_allowlist=body.repo_allowlist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repos = await repo_store.list_repos(session, conn.id)
    return await _connection_card(session, conn, len(repos))


@router.get("/providers/{connection_id}/repos")
async def list_connection_repos(
    connection_id: str, session: AsyncSession = Depends(session_dep)
) -> dict:
    """List every repo the connection's credential can see, plus the current selection.

    This is an explicit management action (operator opened the repo picker), so unlike the
    dashboard read paths it makes a live provider call to enumerate candidates. The current
    allowlist (``None`` ⇒ watching all) is returned so the UI can pre-check the selection.
    """
    row = await repo_store.get_connection_row(session, connection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    connection = conn_service.attach_credential(row.to_domain(), row)
    provider = provider_for(connection)
    try:
        listings = await provider.list_repo_listings(connection)
    except Exception as exc:  # noqa: BLE001 — surface provider failure to the operator
        raise HTTPException(
            status_code=502, detail=f"could not list repos from the provider: {exc}"
        ) from exc
    selected = connection.repo_allowlist
    return {
        "connection_id": connection_id,
        "owner": connection.owner,
        "available": [
            {"name": r.name, "private": r.private}
            for r in sorted(listings, key=lambda r: r.name)
        ],
        "selected": selected,
        "watching_all": selected is None,
    }


class RepoSelection(BaseModel):
    # None / omitted ⇒ watch all repos; a list scopes the fleet to exactly those repos.
    repos: list[str] | None = None


@router.put("/providers/{connection_id}/repos")
async def set_connection_repos(
    connection_id: str,
    body: RepoSelection,
    request: Request,
    background: BackgroundTasks,
    session: AsyncSession = Depends(session_dep),
) -> dict:
    """Replace the connection's repo allowlist, prune de-selected snapshots, then resync.

    Pruning runs inline so de-selected repos leave the dashboard immediately; a background
    sync then interrogates any newly-selected repos (the next scheduled poll would also
    pick them up, but this makes the change feel instant).
    """
    conn = await conn_service.set_repo_allowlist(session, connection_id, body.repos)
    if conn is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    await repo_store.prune_repos_outside_allowlist(session, connection_id, conn.repo_allowlist)
    sync = getattr(request.app.state, "sync", None)
    if sync is not None:
        background.add_task(sync.sync_connection, connection_id)
    repos = await repo_store.list_repos(session, connection_id)
    return await _connection_card(session, conn, len(repos))


class SyncAccepted(BaseModel):
    status: str = "accepted"
    # Echoed for a single-connection refresh; null for a fleet-wide refresh.
    connection_id: str | None = None


@router.post("/providers/sync", status_code=202)
async def trigger_fleet_sync(
    request: Request,
    background: BackgroundTasks,
) -> SyncAccepted:
    """Manually trigger an immediate re-interrogation of every connection (FR-033).

    Returns 202: the work runs in the background on the same path as the scheduled poll
    (no synchronous provider call on the request), so a large fleet can't stall or time out
    the request. The UI refetches the dashboard once the sync lands. A no-op when the
    scheduler isn't running (e.g. under test).
    """
    sync = getattr(request.app.state, "sync", None)
    if sync is not None:
        background.add_task(sync.sync_all)
    return SyncAccepted()


@router.post("/providers/{connection_id}/sync", status_code=202)
async def trigger_connection_sync(
    connection_id: str,
    request: Request,
    background: BackgroundTasks,
    session: AsyncSession = Depends(session_dep),
) -> SyncAccepted:
    """Manually trigger an immediate re-interrogation of one connection's repos (FR-033).

    Same background path as the scheduled poll (so no synchronous provider call blocks the
    request); 404 if the connection is unknown.
    """
    row = await repo_store.get_connection_row(session, connection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    sync = getattr(request.app.state, "sync", None)
    if sync is not None:
        background.add_task(sync.sync_connection, connection_id)
    return SyncAccepted(connection_id=connection_id)


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
