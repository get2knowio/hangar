"""Data-access helpers over the ORM — keep query logic out of services/API."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.domain.models import (
    AuditLogEntry,
    Policy,
    PolicyEntry,
    ProviderConnection,
    RemediationState,
    Repo,
)
from hangar.domain.policy import RemediationMap, default_policy
from hangar.persistence.models import (
    AuditRow,
    ConnectionRow,
    GitHubAppRegistration,
    PolicyRow,
    RemediationRow,
    RepoRow,
)


# --------------------------------------------------------------- connections
async def list_connections(session: AsyncSession) -> list[ProviderConnection]:
    rows = (await session.execute(select(ConnectionRow))).scalars().all()
    return [r.to_domain() for r in rows]


async def get_connection_row(session: AsyncSession, connection_id: str) -> ConnectionRow | None:
    return await session.get(ConnectionRow, connection_id)


async def delete_connection(session: AsyncSession, connection_id: str) -> None:
    """Drop the connection + its repos (cascade); audit rows are retained (clarification)."""
    await session.execute(delete(RepoRow).where(RepoRow.connection_id == connection_id))
    await session.execute(delete(ConnectionRow).where(ConnectionRow.id == connection_id))
    await session.commit()


async def list_connection_rows_for_base_url(
    session: AsyncSession, base_url: str
) -> list[ConnectionRow]:
    """Connections targeting one browser host — the ones a per-host App registration backs.

    Used when removing a connection to find the App's remaining siblings: if none are left, that
    removal was the App's last org, so its stored registration is forgotten too.
    """
    return list(
        (
            await session.execute(
                select(ConnectionRow).where(ConnectionRow.base_url == base_url)
            )
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------- repos
async def list_repos(session: AsyncSession, connection_id: str | None = None) -> list[Repo]:
    stmt = select(RepoRow)
    if connection_id and connection_id != "all":
        stmt = stmt.where(RepoRow.connection_id == connection_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [r.to_domain() for r in rows]


async def prune_repos_outside_allowlist(
    session: AsyncSession, connection_id: str, keep: list[str] | None
) -> int:
    """Delete this connection's repo snapshots whose name is not in ``keep``.

    ``None`` means "no allowlist" (watch all) — nothing is pruned. Returns the row count
    removed. Scoped to ``connection_id`` so a same-named repo on another connection is
    never touched (Constitution I)."""
    if keep is None:
        return 0
    result = await session.execute(
        delete(RepoRow).where(
            RepoRow.connection_id == connection_id,
            RepoRow.id.notin_(keep),
        )
    )
    await session.commit()
    # rowcount lives on the CursorResult; Result's static type doesn't expose it.
    return getattr(result, "rowcount", 0) or 0


async def repo_counts_by_connection(session: AsyncSession) -> dict[str, int]:
    """Repo count per connection in a single grouped query (avoids N+1 on /providers)."""
    rows = await session.execute(
        select(RepoRow.connection_id, func.count()).group_by(RepoRow.connection_id)
    )
    return {cid: n for cid, n in rows.all()}


async def get_repo(
    session: AsyncSession, repo_id: str, connection_id: str
) -> Repo | None:
    # Always resolved by the composite (id, connection_id) PK — never by id alone, which
    # would silently pick one of several same-named repos across connections (Constitution I).
    row = await session.get(RepoRow, (repo_id, connection_id))
    return row.to_domain() if row else None


# -------------------------------------------------------------------- policy
async def get_policy(session: AsyncSession) -> Policy:
    row = await session.get(PolicyRow, "default")
    if row is None:
        policy = default_policy()
        await save_policy(session, policy)
        return policy
    return Policy(
        id=row.id,
        name=row.name,
        entries=[PolicyEntry(**e) for e in (row.entries or [])],
    )


async def save_policy(session: AsyncSession, policy: Policy) -> None:
    row = await session.get(PolicyRow, policy.id)
    entries = [e.model_dump() for e in policy.entries]
    if row is None:
        session.add(PolicyRow(id=policy.id, name=policy.name, entries=entries))
    else:
        row.name = policy.name
        row.entries = entries
    await session.commit()


# --------------------------------------------------------------- remediations
def _rem_key(row: RemediationRow) -> tuple[str, str, str]:
    return (row.connection_id, row.repo_id, row.check_id)


async def remediation_map(
    session: AsyncSession, connection_id: str | None = None
) -> RemediationMap:
    """State overlay for the fleet. Scope to ``connection_id`` when a single connection is
    selected so an overview/scorecard read doesn't scan the whole RemediationRow table for
    a one-connection view (mirrors ``list_repos``' scoping)."""
    stmt = select(RemediationRow)
    if connection_id and connection_id != "all":
        stmt = stmt.where(RemediationRow.connection_id == connection_id)
    rows = (await session.execute(stmt)).scalars().all()
    return {_rem_key(r): RemediationState(r.state) for r in rows}


async def remediation_map_and_pr_urls_for_repo(
    session: AsyncSession, connection_id: str, repo_id: str
) -> tuple[
    RemediationMap,
    dict[tuple[str, str, str], str | None],
    dict[tuple[str, str, str], int | None],
]:
    """State map + PR-url + PR-number overlays for ONE repo (the drill-in path) — a scoped
    query rather than scanning the whole RemediationRow table to render a single repo."""
    rows = (
        await session.execute(
            select(RemediationRow).where(
                RemediationRow.connection_id == connection_id,
                RemediationRow.repo_id == repo_id,
            )
        )
    ).scalars().all()
    state = {_rem_key(r): RemediationState(r.state) for r in rows}
    pr_urls = {_rem_key(r): r.pr_url for r in rows}
    pr_numbers = {_rem_key(r): r.pr_number for r in rows}
    return state, pr_urls, pr_numbers


async def get_remediation(
    session: AsyncSession, connection_id: str, repo_id: str, check_id: str
) -> RemediationRow | None:
    return await session.get(
        RemediationRow,
        {"connection_id": connection_id, "repo_id": repo_id, "check_id": check_id},
    )


async def upsert_remediation(
    session: AsyncSession,
    *,
    connection_id: str,
    repo_id: str,
    check_id: str,
    kind: str,
    state: str,
    pr_url: str | None = None,
    pr_number: int | None = None,
    idempotency_key: str | None = None,
) -> RemediationRow:
    row = await session.get(
        RemediationRow,
        {"connection_id": connection_id, "repo_id": repo_id, "check_id": check_id},
    )
    if row is None:
        row = RemediationRow(connection_id=connection_id, repo_id=repo_id, check_id=check_id)
        row.created_at = datetime.now(UTC)  # set once, on creation
        session.add(row)
    row.kind = kind
    row.state = state
    row.pr_url = pr_url
    row.pr_number = pr_number
    row.idempotency_key = idempotency_key
    await session.commit()
    return row


# ------------------------------------------------------------------- audit
async def append_audit(session: AsyncSession, entry: AuditLogEntry) -> AuditLogEntry:
    row = AuditRow(
        timestamp=entry.timestamp,
        connection_label=entry.connection_label,
        actor=entry.actor,
        repo_id=entry.repo_id,
        check_label=entry.check_label,
        result=entry.result,
        pr_url=entry.pr_url,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    entry.id = row.id
    return entry


async def get_audit(session: AsyncSession, audit_id: int) -> AuditLogEntry | None:
    r = await session.get(AuditRow, audit_id)
    if r is None:
        return None
    return AuditLogEntry(
        id=r.id, timestamp=r.timestamp, connection_label=r.connection_label, actor=r.actor,
        repo_id=r.repo_id, check_label=r.check_label, result=r.result, pr_url=r.pr_url,
    )


async def list_audit(session: AsyncSession, limit: int = 50) -> list[AuditLogEntry]:
    rows = (
        (await session.execute(select(AuditRow).order_by(AuditRow.id.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return [
        AuditLogEntry(
            id=r.id,
            timestamp=r.timestamp,
            connection_label=r.connection_label,
            actor=r.actor,
            repo_id=r.repo_id,
            check_label=r.check_label,
            result=r.result,
            pr_url=r.pr_url,
        )
        for r in rows
    ]


async def next_pr_number(session: AsyncSession) -> int:
    """Monotonic PR number for demo corrections (prototype ``prCounter`` seeded at 142).

    Uses SQL ``MAX`` so the database returns one scalar instead of streaming every
    pr_number into Python to max() it (the table grows with every remediation)."""
    current = (await session.execute(select(func.max(RemediationRow.pr_number)))).scalar()
    return (current if current is not None else 142) + 1


# ------------------------------------------------------- github app registrations
async def get_app_registration(
    session: AsyncSession, base_url: str
) -> GitHubAppRegistration | None:
    """The GitHub App provisioned for ``base_url`` (one per host), or None."""
    return await session.get(GitHubAppRegistration, base_url)


async def upsert_app_registration(
    session: AsyncSession,
    *,
    base_url: str,
    app_id: str,
    slug: str,
    client_id: str | None,
    private_key_ciphertext: bytes,
    webhook_secret_ciphertext: bytes | None,
    client_secret_ciphertext: bytes | None,
) -> GitHubAppRegistration:
    """Create or replace the App registration for ``base_url`` (re-provisioning overwrites)."""
    row = await session.get(GitHubAppRegistration, base_url)
    if row is None:
        row = GitHubAppRegistration(base_url=base_url)
        session.add(row)
    row.app_id = app_id
    row.slug = slug
    row.client_id = client_id
    row.private_key_ciphertext = private_key_ciphertext
    row.webhook_secret_ciphertext = webhook_secret_ciphertext
    row.client_secret_ciphertext = client_secret_ciphertext
    row.created_at = datetime.now(UTC)
    await session.commit()
    return row


async def delete_app_registration(session: AsyncSession, base_url: str) -> bool:
    """Forget the stored GitHub App registration for ``base_url`` (drops its credentials).

    Returns True if a row was removed, False if none existed. Local-only: this discards
    Hangar's copy of the App's private key — it does not touch the App on GitHub (that is a
    manual delete the operator finishes via a deep link).
    """
    result = await session.execute(
        delete(GitHubAppRegistration).where(GitHubAppRegistration.base_url == base_url)
    )
    await session.commit()
    return bool(getattr(result, "rowcount", 0))


async def list_app_registrations(session: AsyncSession) -> list[GitHubAppRegistration]:
    """Every stored per-host App registration (non-secret fields used to surface 'forget')."""
    return list((await session.execute(select(GitHubAppRegistration))).scalars().all())
