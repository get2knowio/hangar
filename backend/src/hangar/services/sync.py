"""Per-connection sync poller (Constitution VI; FR-034–FR-038, SC-003/SC-009/SC-010).

An APScheduler job polls each configured connection on a cadence, interrogates its
repos through the provider adapter, and writes normalized snapshots to the cache with a
fresh ``last_sync``. Newly discovered repos in a connected scope are auto-evaluated on
the next sync with zero per-repo setup (FR-034, SC-003).

Resilience: a provider outage is swallowed per-connection — the last good snapshot is
retained and the connection's ``last_sync`` ages, surfacing staleness (FR-035/FR-036,
SC-009). Reads never trigger live calls; only the poller/webhooks do (SC-010). A simple
per-connection token budget caps calls per cycle.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from hangar.config import get_settings
from hangar.persistence import repositories as repo
from hangar.persistence.db import get_sessionmaker
from hangar.persistence.models import ConnectionRow, RepoRow
from hangar.persistence.seed import seed_if_empty
from hangar.providers.registry import provider_for

log = structlog.get_logger(__name__)


def format_relative(dt: datetime | None, *, now: datetime | None = None) -> str:
    """Humanize a timestamp as the prototype's ``synced 2m ago`` strings."""
    if dt is None:
        return "never"
    now = now or datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    if secs < 172800:
        return "yesterday"
    return f"{secs // 86400}d ago"


def is_stale(dt: datetime | None, *, now: datetime | None = None) -> bool:
    if dt is None:
        return True
    now = now or datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (now - dt) > timedelta(seconds=get_settings().stale_after_seconds)


class SyncService:
    """Owns the scheduler and per-connection budgets."""

    def __init__(self, sessionmaker: async_sessionmaker | None = None) -> None:
        self._sessionmaker = sessionmaker or get_sessionmaker()
        self._scheduler = None

    async def ensure_seed(self) -> None:
        if not get_settings().seed_demo_data:
            return
        async with self._sessionmaker() as session:
            seeded = await seed_if_empty(session)
            if seeded:
                log.info("sync.seeded", source="prototype-fixtures")

    async def sync_connection(self, connection_id: str) -> int:
        """Interrogate every repo in a connection's scope; returns repos updated.

        Wrapped so a provider outage degrades to "serve last snapshot" rather than
        propagating (SC-009).
        """
        budget = 500  # per-connection token budget per cycle
        async with self._sessionmaker() as session:
            row = await session.get(ConnectionRow, connection_id)
            if row is None:
                return 0
            connection = row.to_domain()
            from hangar.services.connections import attach_credential

            attach_credential(connection, row)
            provider = provider_for(connection)
            updated = 0
            try:
                refs = await provider.list_repos(connection)
                for ref in refs[:budget]:
                    snapshot = await provider.interrogate(connection, ref)
                    if snapshot is None:
                        continue  # 304 Not Modified — keep the cached snapshot (SC-010)
                    await self._upsert_repo(session, snapshot)
                    updated += 1
                row.last_sync_at = datetime.now(UTC)
                await session.commit()
            except Exception as exc:  # noqa: BLE001 - resilience boundary
                log.warning(
                    "sync.connection_failed",
                    connection=connection_id, error=str(exc),
                    note="serving last good snapshot",
                )
            return updated

    async def _upsert_repo(self, session, snapshot) -> None:
        # Key on (id, connection_id) so a repo of the same name under another connection
        # is never overwritten (composite PK).
        row = await session.get(RepoRow, (snapshot.id, snapshot.connection_id))
        if row is None:
            row = RepoRow(id=snapshot.id, connection_id=snapshot.connection_id)
            session.add(row)
        row.description = snapshot.description
        row.default_branch = snapshot.default_branch
        row.open_prs = snapshot.open_prs
        row.dependabot_prs = snapshot.dependabot_prs
        row.ci_status = snapshot.ci_status.value
        row.alerts = {
            "critical": snapshot.alerts.critical, "high": snapshot.alerts.high,
            "moderate": snapshot.alerts.moderate, "low": snapshot.alerts.low,
        }
        row.release_pending_days = snapshot.release_pending_days
        row.fails = snapshot.fails
        row.unknowns = snapshot.unknowns
        row.last_evaluated_at = datetime.now(UTC)

    async def sync_all(self) -> None:
        async with self._sessionmaker() as session:
            connections = await repo.list_connections(session)
        for connection in connections:
            await self.sync_connection(connection.id)

    def start(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        self._scheduler = AsyncIOScheduler()
        interval = get_settings().poll_interval_seconds
        self._scheduler.add_job(self.sync_all, "interval", seconds=interval, id="poll-all")
        self._scheduler.start()
        log.info("sync.scheduler_started", interval_seconds=interval)

    def shutdown(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
