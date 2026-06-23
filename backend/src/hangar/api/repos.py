"""Repo drill-down + remediation endpoints (Story 3; FR-011–FR-018)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from hangar.api.deps import actor_dep, session_dep
from hangar.domain.checks import CATALOG
from hangar.domain.models import RemediationKind, kind_for_tier
from hangar.domain.remediation import NoOpenPullRequest, ReadOnlyCollapse, RemediationService
from hangar.persistence import repositories as repo_store
from hangar.providers.registry import provider_for
from hangar.services.connections import attach_credential
from hangar.services.fleet_remediation import remediate_check_across
from hangar.services.repo_detail import build_repo_detail

router = APIRouter(tags=["repos"])


@router.get("/repos/{connection_id}/{repo_id}")
async def repo_detail(
    connection_id: str, repo_id: str, session: AsyncSession = Depends(session_dep)
) -> dict:
    repo = await repo_store.get_repo(session, repo_id, connection_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    conn_row = await repo_store.get_connection_row(session, connection_id)
    if conn_row is None:
        raise HTTPException(status_code=404, detail="connection not found")
    connection = conn_row.to_domain()
    # Scoped load: just this connection's policy + this repo's remediation overlay — never
    # the whole fleet/remediation table to render one repo.
    policy = await repo_store.get_policy(session)
    remediations, pr_urls, pr_numbers = await repo_store.remediation_map_and_pr_urls_for_repo(
        session, connection_id, repo_id
    )
    return build_repo_detail(repo, connection, policy, remediations, pr_urls, pr_numbers)


class RemediateBody(BaseModel):
    kind: RemediationKind


def _write_kind_for(check_id: str) -> RemediationKind:
    """Resolve the server-authoritative remediation kind from the check's tier.

    Maps every tier (not just patch vs pr) so a link-tier check resolves to a deep-link
    rather than wrongly attempting a config PR.
    """
    return kind_for_tier(CATALOG[check_id].tier)


@router.post("/repos/{connection_id}/{repo_id}/checks/{check_id}/remediate", response_model=None)
async def remediate(
    connection_id: str,
    repo_id: str,
    check_id: str,
    body: RemediateBody,
    session: AsyncSession = Depends(session_dep),
    actor: str = Depends(actor_dep),
) -> dict | JSONResponse:
    repo = await repo_store.get_repo(session, repo_id, connection_id)
    if repo is None or check_id not in CATALOG:
        raise HTTPException(status_code=404, detail="repo or check not found")
    conn_row = await repo_store.get_connection_row(session, repo.connection_id)
    if conn_row is None:
        raise HTTPException(status_code=404, detail="connection not found")
    connection = conn_row.to_domain()
    # Decrypt and attach the stored credential so live (writable) connections can actually
    # reach the provider — without this a real GitHub App connection raises in _client.
    attach_credential(connection, conn_row)

    # Resolve the effective write kind server-side; never trust the client to pick a
    # write kind a check/connection doesn't support.
    kind: RemediationKind
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


class BatchTarget(BaseModel):
    connection_id: str
    repo_id: str


class RemediateBatchBody(BaseModel):
    targets: list[BatchTarget]


@router.post("/checks/{check_id}/remediate-batch")
async def remediate_batch(
    check_id: str,
    body: RemediateBatchBody,
    session: AsyncSession = Depends(session_dep),
    actor: str = Depends(actor_dep),
) -> dict:
    """Fleet-wide remediation: apply ``check_id`` across many repos in one operator action.

    Each target is corrected via the same PR-first, idempotent, per-repo-audited path; the
    kind is resolved server-side and read-only connections collapse to a deep-link. Results
    are reported per target with a status roll-up.
    """
    if check_id not in CATALOG:
        raise HTTPException(status_code=404, detail="check not found")
    results = await remediate_check_across(
        session,
        check_id=check_id,
        targets=[(t.connection_id, t.repo_id) for t in body.targets],
        actor=actor,
    )
    summary: dict[str, int] = {}
    for r in results:
        summary[r.status] = summary.get(r.status, 0) + 1
    return {
        "check_id": check_id,
        "results": [
            {
                "connection_id": r.connection_id,
                "repo_id": r.repo_id,
                "status": r.status,
                "pr_url": r.pr_url,
                "deep_link_url": r.deep_link_url,
                "idempotent_hit": r.idempotent_hit,
                "detail": r.detail,
            }
            for r in results
        ],
        "summary": summary,
    }


@router.post("/repos/{connection_id}/{repo_id}/checks/{check_id}/merge")
async def mark_merged(
    connection_id: str,
    repo_id: str,
    check_id: str,
    session: AsyncSession = Depends(session_dep),
    actor: str = Depends(actor_dep),
) -> dict:
    """Mark a Hangar-authored PR merged → finding flips to pass (prototype ``markMerged``)."""
    repo = await repo_store.get_repo(session, repo_id, connection_id)
    if repo is None or check_id not in CATALOG:
        raise HTTPException(status_code=404, detail="repo or check not found")
    conn_row = await repo_store.get_connection_row(session, repo.connection_id)
    if conn_row is None:
        raise HTTPException(status_code=404, detail="connection not found")
    connection = conn_row.to_domain()
    attach_credential(connection, conn_row)
    service = RemediationService(provider_for(connection))
    try:
        outcome = await service.mark_merged(
            session, connection=connection, repo=repo, check_id=check_id, actor=actor
        )
    except NoOpenPullRequest as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"state": outcome.state.value, "pr_url": outcome.pr_url, "idempotent_hit": False}
