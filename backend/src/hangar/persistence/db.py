"""Async SQLAlchemy engine/session (SQLite default; Postgres via HANGAR_POSTGRES_* or URL).

The same ORM models target both engines (Constitution V — SQLite default, Postgres
documented upgrade). The URL is resolved by ``Settings.effective_database_url`` (discrete
HANGAR_POSTGRES_* vars, else HANGAR_DATABASE_URL / the SQLite default).

Startup calls :func:`apply_migrations`, which brings the database to head under Alembic
management (packaged migrations at ``hangar/migrations``): a fresh DB is created and stamped,
an already-managed DB is upgraded (so renames/drops/type-changes apply), and a legacy
``create_all`` DB (the pre-Alembic in-the-wild case) is additively reconciled then stamped —
guarded against non-additive drift so a rename can't silently orphan data. It fails closed on
any error rather than serving a half-migrated schema, and serializes replicas via a Postgres
advisory lock. :func:`ensure_schema` (create_all + additive column reconcile) remains as the
reusable additive-heal building block.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config
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


class SchemaMigrationError(RuntimeError):
    """The database cannot be safely migrated on startup — fail closed rather than serve."""


# Advisory-lock key (a bigint) so concurrent replicas serialize their migration run on
# Postgres; arbitrary fixed constant ("HANG"). SQLite is single-node, so it's a no-op there.
_MIGRATION_LOCK_KEY = 0x48414E47


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


def _migrations_dir() -> Path:
    """Absolute path to the packaged Alembic migrations (they ship inside the wheel, so this
    resolves identically in a dev checkout and in the container — no CWD dependence)."""
    return Path(__file__).resolve().parent.parent / "migrations"


def _alembic_config() -> Config:
    """Build an Alembic ``Config`` programmatically (no ini needed at runtime).

    ``env.py`` resolves the database URL from Settings itself, so only ``script_location``
    has to be pinned to the packaged migrations directory.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(_migrations_dir()))
    return cfg


def _run_alembic(action: str) -> None:
    """Run an Alembic command synchronously — MUST be called inside a worker thread.

    ``env.py`` drives its own async engine via ``asyncio.run``; invoking these on the app's
    running event loop would raise "asyncio.run() cannot be called from a running loop".
    """
    cfg = _alembic_config()
    if action == "upgrade":
        command.upgrade(cfg, "head")
    elif action == "stamp":
        command.stamp(cfg, "head")
    else:  # pragma: no cover - programmer error
        raise ValueError(f"unknown alembic action: {action}")


def _classify_schema(sync_conn: Connection) -> str:
    """Classify the database as ``managed`` (Alembic-stamped), ``legacy`` (a ``create_all``
    database with app tables but no ``alembic_version``), or ``fresh`` (no app tables)."""
    inspector = inspect(sync_conn)
    if inspector.has_table("alembic_version"):
        return "managed"
    model_tables = {t.name for t in Base.metadata.sorted_tables}
    present = set(inspector.get_table_names())
    return "legacy" if model_tables & present else "fresh"


def _orphan_columns(sync_conn: Connection) -> list[tuple[str, str]]:
    """DB columns absent from the current ORM models — evidence of a rename/drop that
    additive reconciliation cannot heal without orphaning data (e.g. the pre-0.3.2
    ``repos.dependabot_prs`` that predates its rename to ``bot_prs``)."""
    inspector = inspect(sync_conn)
    orphans: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        model_cols = {c.name for c in table.columns}
        db_cols = {c["name"] for c in inspector.get_columns(table.name)}
        orphans.extend((table.name, col) for col in sorted(db_cols - model_cols))
    return orphans


@asynccontextmanager
async def _migration_lock(engine: AsyncEngine) -> AsyncIterator[None]:
    """Serialize the migration critical section across replicas.

    Postgres takes a session-level advisory lock (blocking, so a second replica waits rather
    than racing); SQLite is single-node and needs none.
    """
    if engine.dialect.name != "postgresql":
        yield
        return
    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _MIGRATION_LOCK_KEY})
        try:
            yield
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _MIGRATION_LOCK_KEY})


async def apply_migrations() -> None:
    """Bring the database to the current schema at startup, under Alembic management.

    Fail-closed: any error propagates, so the app refuses to serve a half-migrated schema.
    Branches on the database's state:

    * **fresh** (no app tables) → :func:`create_all` + ``alembic stamp head``.
    * **legacy** (a ``create_all`` database with no ``alembic_version``) → additive column
      reconcile, then — guarded against non-additive drift (any DB column absent from the
      models, e.g. ``repos.dependabot_prs`` on a v0.1.0–v0.3.1 install) — ``alembic stamp head``.
      The guard fails closed instead of stamping, because stamping would falsely declare the
      rename applied while the real data sits in the orphaned column.
    * **managed** (already Alembic-stamped) → ``alembic upgrade head`` — now renames, drops,
      and type changes apply correctly.

    Replaces the older unconditional :func:`ensure_schema`; concurrent replicas serialize via
    a Postgres advisory lock.
    """
    from hangar.persistence import models  # noqa: F401 — register tables on Base.metadata

    engine = get_engine()
    async with _migration_lock(engine):
        async with engine.connect() as conn:
            state = await conn.run_sync(_classify_schema)

        if state == "managed":
            log.info("schema.migrate.upgrade", state=state)
            await asyncio.to_thread(_run_alembic, "upgrade")
        elif state == "fresh":
            log.info("schema.migrate.fresh", state=state)
            await create_all()
            await asyncio.to_thread(_run_alembic, "stamp")
        else:  # legacy create_all database
            log.info("schema.migrate.legacy_reconcile", state=state)
            await create_all()  # any wholly-absent tables (additive)
            engine2 = get_engine()
            async with engine2.begin() as conn:
                await conn.run_sync(_reconcile_columns)
            async with engine2.connect() as conn:
                orphans = await conn.run_sync(_orphan_columns)
            if orphans:
                cols = ", ".join(f"{t}.{c}" for t, c in orphans)
                raise SchemaMigrationError(
                    "Refusing to auto-manage a database with columns the current models do not "
                    f"define ({cols}). This is a rename/drop that additive reconciliation cannot "
                    "heal without orphaning data — e.g. the pre-0.3.2 'repos.dependabot_prs' → "
                    "'bot_prs' rename. Migrate manually: back up the database, apply the "
                    "equivalent change, then run `alembic stamp head`."
                )
            await asyncio.to_thread(_run_alembic, "stamp")
    log.info("schema.migrate.complete", state=state)


async def reset_engine() -> None:
    """Dispose engine/sessionmaker (used by tests switching DB URLs)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
