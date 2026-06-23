"""Fleet-wide (bulk) remediation — apply one check's correction across many repos.

Runs the single-repo :class:`~hangar.domain.remediation.RemediationService` over a set of
``(connection_id, repo_id)`` targets for one check. Every guarantee of the single path
holds per target: operator-triggered, PR-first, idempotent, one audit entry per repo, and
the server resolves the effective kind (never the client). A read-only connection collapses
to a deep-link, and a single target's failure is isolated so it never aborts the batch
(mirrors the per-repo isolation in the sync poller).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.domain.checks import CATALOG
from hangar.domain.models import ProviderConnection, RemediationKind, kind_for_tier
from hangar.domain.remediation import ReadOnlyCollapse, RemediationService
from hangar.persistence import repositories as repo_store
from hangar.providers.registry import provider_for
from hangar.services.connections import attach_credential

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class TargetResult:
    connection_id: str
    repo_id: str
    status: str  # pr_open | fixed | deep_link | not_found | error
    pr_url: str | None = None
    deep_link_url: str | None = None
    idempotent_hit: bool = False
    detail: str | None = None


async def remediate_check_across(
    session: AsyncSession,
    *,
    check_id: str,
    targets: list[tuple[str, str]],
    actor: str,
) -> list[TargetResult]:
    """Remediate ``check_id`` on each ``(connection_id, repo_id)`` target.

    Raises KeyError if the check is unknown. Per-target outcomes (including read-only
    collapse and isolated errors) are returned, never raised.
    """
    if check_id not in CATALOG:
        raise KeyError(check_id)

    # Server-authoritative kind from the check's native tier (the service collapses write
    # kinds on read-only connections) — the client never picks the kind for a bulk run.
    kind: RemediationKind = kind_for_tier(CATALOG[check_id].tier)

    # Each connection is loaded once (credential attached); many targets share one.
    cache: dict[str, tuple[ProviderConnection, RemediationService] | None] = {}

    async def _load(connection_id: str) -> tuple[ProviderConnection, RemediationService] | None:
        if connection_id not in cache:
            row = await repo_store.get_connection_row(session, connection_id)
            if row is None:
                cache[connection_id] = None
            else:
                connection = row.to_domain()
                attach_credential(connection, row)
                cache[connection_id] = (connection, RemediationService(provider_for(connection)))
        return cache[connection_id]

    results: list[TargetResult] = []
    seen: set[tuple[str, str]] = set()
    for connection_id, repo_id in targets:
        if (connection_id, repo_id) in seen:
            continue
        seen.add((connection_id, repo_id))

        loaded = await _load(connection_id)
        if loaded is None:
            results.append(TargetResult(connection_id, repo_id, "not_found", detail="unknown connection"))
            continue
        connection, service = loaded
        repo = await repo_store.get_repo(session, repo_id, connection_id)
        if repo is None:
            results.append(TargetResult(connection_id, repo_id, "not_found", detail="repo not found"))
            continue

        try:
            outcome = await service.remediate(
                session, connection=connection, repo=repo, check_id=check_id, kind=kind, actor=actor
            )
            results.append(
                TargetResult(
                    connection_id, repo_id, outcome.state.value,
                    pr_url=outcome.pr_url, idempotent_hit=outcome.idempotent_hit,
                )
            )
        except ReadOnlyCollapse as collapse:
            results.append(
                TargetResult(connection_id, repo_id, "deep_link", deep_link_url=collapse.deep_link_url)
            )
        except Exception as exc:  # noqa: BLE001 - isolate per target; one repo never aborts the batch
            await session.rollback()
            log.warning(
                "remediate_batch.target_failed",
                connection=connection_id, repo=repo_id, check=check_id, error=str(exc),
            )
            results.append(TargetResult(connection_id, repo_id, "error", detail=str(exc)))

    return results
