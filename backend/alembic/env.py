"""Alembic environment — async SQLAlchemy, schema owned by Hangar's ORM.

The database URL is read from ``HANGAR_DATABASE_URL`` (falling back to Hangar's
``Settings``), and the target metadata is ``hangar.persistence.db.Base.metadata``.
Importing ``hangar.persistence.models`` registers every table on that metadata so
autogenerate and ``create_all`` see the full schema.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

# Import models so every table registers on Base.metadata.
from hangar.persistence import models  # noqa: F401
from hangar.persistence.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.environ.get("HANGAR_DATABASE_URL")
    if url:
        return url
    try:
        from hangar.config import get_settings

        return get_settings().database_url
    except Exception:  # pragma: no cover - settings unavailable
        return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no DBAPI)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # batch mode for SQLite ALTER support
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode against an async engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
