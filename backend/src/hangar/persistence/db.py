"""Async SQLAlchemy engine/session (SQLite default; Postgres via HANGAR_POSTGRES_* or URL).

The same ORM models target both engines (Constitution V — SQLite default, Postgres
documented upgrade). The URL is resolved by ``Settings.effective_database_url`` (discrete
HANGAR_POSTGRES_* vars, else HANGAR_DATABASE_URL / the SQLite default).

Startup calls :func:`ensure_schema`, which creates missing tables *and* reconciles missing
columns against the ORM metadata. This matters for in-place image upgrades: ``create_all``
alone only creates absent tables, so a release that added a column to a pre-existing table
left it missing and every query failed (e.g. ``no such column: repos.suppressions``).
Reconciliation is additive/nullable-safe; non-additive changes (renames/drops/type changes)
are logged for manual handling, not auto-applied.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import CreateColumn

from hangar.config import get_settings

log = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all persistence models."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = get_settings().effective_database_url
        is_sqlite = url.startswith("sqlite")
        # SQLite needs check_same_thread off for the async driver pool. Postgres benefits
        # from pre-ping so a long-running poller survives dropped idle connections.
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        _engine = create_async_engine(
            url, future=True, connect_args=connect_args, pool_pre_ping=not is_sqlite
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a session, rolls back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def create_all() -> None:
    # Import models so they register on Base.metadata before create_all.
    from hangar.persistence import models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ensure_schema() -> None:
    """Bring the database up to the current ORM schema at startup (idempotent).

    Runs :func:`create_all` (adds missing tables) then reconciles missing *columns* against
    the ORM metadata — the schema drift an in-place image upgrade produces when a release
    adds a column to a table an older version already created. Additive and nullable-safe:
    a NOT NULL column without a default can't be back-filled here, so it is logged and
    skipped rather than failing startup. Renames/drops/type-changes are not handled.
    """
    from hangar.persistence import models  # noqa: F401 — register tables on Base.metadata

    await create_all()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(_reconcile_columns)


def _reconcile_columns(conn: Connection) -> None:
    """Add any model columns absent from an existing table (in-place ALTER ... ADD COLUMN)."""
    inspector = inspect(conn)
    dialect = conn.dialect
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue  # create_all already handles wholly-absent tables
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            if not column.nullable and column.default is None and column.server_default is None:
                log.warning(
                    "schema.reconcile.skipped_non_nullable_column",
                    table=table.name,
                    column=column.name,
                    detail="needs a data-migration; add it manually",
                )
                continue
            spec = CreateColumn(column).compile(dialect=dialect)
            conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {spec}'))
            log.info("schema.reconcile.added_column", table=table.name, column=column.name)


async def reset_engine() -> None:
    """Dispose engine/sessionmaker (used by tests switching DB URLs)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
