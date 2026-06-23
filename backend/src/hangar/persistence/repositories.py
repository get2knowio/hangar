"""Data-access helpers over the ORM — keep query logic out of services/API."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
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


# ---------------------------------------------------------------------- repos
async def list_repos(session: AsyncSession, connection_id: str | None = None) -> list[Repo]:
    stmt = select(RepoRow)
    if connection_id and connection_id != "all":
        stmt = stmt.where(RepoRow.connection_id == connection_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [r.to_domain() for r in rows]


async def repo_counts_by_connection(session: AsyncSession) -> dict[str, int]:
    """Repo count per connection in a single grouped query (avoids N+1 on /providers)."""
    from sqlalchemy import func

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


async def remediation_map(session: AsyncSession) -> RemediationMap:
    rows = (await session.execute(select(RemediationRow))).scalars().all()
    return {_rem_key(r): RemediationState(r.state) for r in rows}


async def remediation_map_and_pr_urls(
    session: AsyncSession,
) -> tuple[RemediationMap, dict[tuple[str, str, str], str | None]]:
    """State map + PR-url overlay in a single RemediationRow scan (repo-detail path)."""
    rows = (await session.execute(select(RemediationRow))).scalars().all()
    state = {_rem_key(r): RemediationState(r.state) for r in rows}
    pr_urls = {_rem_key(r): r.pr_url for r in rows}
    return state, pr_urls


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
    """Monotonic PR number for demo corrections (prototype ``prCounter`` seeded at 142)."""
    rows = (await session.execute(select(RemediationRow.pr_number))).scalars().all()
    existing = [n for n in rows if n is not None]
    return (max(existing) if existing else 142) + 1
