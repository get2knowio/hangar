"""Repo drill-down + remediation endpoints (Story 3; FR-011–FR-018)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from hangar.api.deps import actor_dep, load_fleet, session_dep
from hangar.domain.checks import CATALOG
from hangar.domain.models import RemediationKind, RemediationTier
from hangar.domain.remediation import ReadOnlyCollapse, RemediationService
from hangar.persistence import repositories as repo_store
from hangar.providers.registry import provider_for
from hangar.services.connections import attach_credential
from hangar.services.repo_detail import build_repo_detail

router = APIRouter(tags=["repos"])


@router.get("/repos/{repo_id}")
async def repo_detail(
    repo_id: str, session: AsyncSession = Depends(session_dep)
) -> dict:
    repo = await repo_store.get_repo(session, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    ctx = await load_fleet(session, "all", with_pr_urls=True)
    connection = ctx.connections.get(repo.connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="connection not found")
    return build_repo_detail(repo, connection, ctx.policy, ctx.remediations, ctx.rem_pr_urls)


class RemediateBody(BaseModel):
    kind: RemediationKind


def _write_kind_for(check_id: str) -> RemediationKind:
    check = CATALOG[check_id]
    return (
        RemediationKind.settings_patch
        if check.tier is RemediationTier.patch
        else RemediationKind.config_pr
    )


@router.post("/repos/{repo_id}/checks/{check_id}/remediate")
async def remediate(
    repo_id: str,
    check_id: str,
    body: RemediateBody,
    session: AsyncSession = Depends(session_dep),
    actor: str = Depends(actor_dep),
):
    repo = await repo_store.get_repo(session, repo_id)
    if repo is None or check_id not in CATALOG:
        raise HTTPException(status_code=404, detail="repo or check not found")
    conn_row = await repo_store.get_connection_row(session, repo.connection_id)
    if conn_row is None:
        raise HTTPException(status_code=404, detail="connection not found")
    connection = conn_row.to_domain()

    # Resolve the effective write kind server-side; never trust the client to pick a
    # write kind a check/connection doesn't support.
    if body.kind in (RemediationKind.report, RemediationKind.deep_link):
        kind = body.kind
    else:
        kind = _write_kind_for(check_id)

    service = RemediationService(provider_for(connection))
    try:
        outcome = await service.remediate(
            session, connection=connection, repo=repo, check_id=check_id, kind=kind, actor=actor
        )
    except ReadOnlyCollapse as collapse:
        return JSONResponse(status_code=403, content={"deep_link_url": collapse.deep_link_url})

    audit = None
    if outcome.audit_id is not None:
        # Fetch the exact entry this call produced — never "the newest row", which races
        # against concurrent remediations and could echo another correction's audit.
        e = await repo_store.get_audit(session, outcome.audit_id)
        if e is not None:
            audit = {
                "timestamp": "just now", "repo_id": e.repo_id, "check_label": e.check_label,
                "connection_label": e.connection_label, "actor": e.actor,
                "result": e.result, "pr_url": e.pr_url,
            }
    return {
        "state": outcome.state.value,
        "pr_url": outcome.pr_url,
        "audit": audit,
        "idempotent_hit": outcome.idempotent_hit,
    }


@router.post("/repos/{repo_id}/checks/{check_id}/merge")
async def mark_merged(
    repo_id: str,
    check_id: str,
    session: AsyncSession = Depends(session_dep),
    actor: str = Depends(actor_dep),
) -> dict:
    """Mark a Hangar-authored PR merged → finding flips to pass (prototype ``markMerged``)."""
    repo = await repo_store.get_repo(session, repo_id)
    if repo is None or check_id not in CATALOG:
        raise HTTPException(status_code=404, detail="repo or check not found")
    conn_row = await repo_store.get_connection_row(session, repo.connection_id)
    if conn_row is None:
        raise HTTPException(status_code=404, detail="connection not found")
    connection = conn_row.to_domain()
    attach_credential(connection, conn_row)
    service = RemediationService(provider_for(connection))
    outcome = await service.mark_merged(
        session, connection=connection, repo=repo, check_id=check_id, actor=actor
    )
    return {"state": outcome.state.value, "pr_url": outcome.pr_url, "idempotent_hit": False}
