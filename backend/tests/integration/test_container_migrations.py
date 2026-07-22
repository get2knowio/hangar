"""Container-startup migrations (issue #50).

``apply_migrations`` classifies the database and brings it to head under Alembic
management, replacing the old unconditional ``ensure_schema``:

* **fresh** install → ``create_all`` + ``stamp head``,
* **legacy** ``create_all`` database (no ``alembic_version``) → additive reconcile then
  ``stamp head``, guarded against non-additive drift (fails closed),
* **managed** database → ``alembic upgrade head`` (renames/drops/type-changes apply),

and startup fails loudly on any migration error rather than serving a half-migrated schema.
"""

from __future__ import annotations

import asyncio

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from hangar.persistence.db import (
    SchemaMigrationError,
    _alembic_config,
    apply_migrations,
    create_all,
    get_engine,
)

HEAD = "d9e0f1a2b3c4"
PRE_RENAME = "b7c8d9e0f1a2"  # down_revision of the dependabot_prs -> bot_prs rename


async def _alembic_version() -> str | None:
    def _read(sync_conn: Connection) -> str | None:
        if not inspect(sync_conn).has_table("alembic_version"):
            return None
        return sync_conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()

    async with get_engine().connect() as conn:
        return await conn.run_sync(_read)


async def _has_column(table: str, col: str) -> bool:
    def _check(sync_conn: Connection) -> bool:
        insp = inspect(sync_conn)
        if not insp.has_table(table):
            return False
        return col in {c["name"] for c in insp.get_columns(table)}

    async with get_engine().connect() as conn:
        return await conn.run_sync(_check)


def _insert_pre_rename_repo(sync_conn: Connection, bot_pr_count: int) -> None:
    """Insert one repos row into the historical (pre-rename) schema, setting dependabot_prs.

    Introspects the table so it stays valid whatever the exact NOT NULL set was at that
    revision — supplying a type-appropriate value for every required column.
    """
    values: dict[str, object] = {}
    for c in inspect(sync_conn).get_columns("repos"):
        name = c["name"]
        if name == "dependabot_prs":
            values[name] = bot_pr_count
            continue
        if c.get("nullable", True):
            continue  # optional — leave it NULL
        type_ = str(c["type"]).upper()
        if name == "id":
            values[name] = "r1"
        elif "INT" in type_:
            values[name] = 0
        elif "JSON" in type_:
            values[name] = "[]"
        else:  # VARCHAR / TEXT / etc.
            values[name] = "x"
    columns = ", ".join(values)
    placeholders = ", ".join(f":{k}" for k in values)
    sync_conn.execute(text(f"INSERT INTO repos ({columns}) VALUES ({placeholders})"), values)


async def test_fresh_database_converges_to_head() -> None:
    """No app tables → create_all + stamp head, so the DB is queryable and Alembic-managed."""
    await apply_migrations()
    assert await _alembic_version() == HEAD
    assert await _has_column("repos", "bot_prs")


async def test_legacy_create_all_db_is_stamped_to_head() -> None:
    """A create_all DB (current schema, no alembic_version) is reconciled then stamped."""
    await create_all()
    assert await _alembic_version() is None  # not yet under Alembic management
    await apply_migrations()
    assert await _alembic_version() == HEAD


async def test_legacy_db_with_pre_rename_column_fails_closed() -> None:
    """The orphan guard refuses to stamp a DB carrying a pre-rename column (data-loss risk).

    Reproduces a v0.1.0–v0.3.1 install: its create_all DB carried ``dependabot_prs``, which a
    later create_all/reconcile left orphaned alongside the new ``bot_prs``. Stamping head here
    would falsely declare the rename applied while the real counts sit in the orphan column.
    """
    await create_all()
    async with get_engine().begin() as conn:
        await conn.execute(text("ALTER TABLE repos ADD COLUMN dependabot_prs INTEGER"))

    with pytest.raises(SchemaMigrationError, match="dependabot_prs"):
        await apply_migrations()

    assert await _alembic_version() is None  # guard did not stamp — left for manual repair


async def test_managed_db_applies_rename_preserving_data() -> None:
    """A managed DB runs real migrations on upgrade: the rename carries data across."""
    # Build the genuine historical schema at the rename's parent revision.
    await asyncio.to_thread(command.upgrade, _alembic_config(), PRE_RENAME)
    assert await _alembic_version() == PRE_RENAME
    assert await _has_column("repos", "dependabot_prs")

    async with get_engine().begin() as conn:
        await conn.run_sync(_insert_pre_rename_repo, 7)

    await apply_migrations()  # managed → upgrade head

    assert await _alembic_version() == HEAD
    assert await _has_column("repos", "bot_prs")
    assert not await _has_column("repos", "dependabot_prs")
    async with get_engine().connect() as conn:
        carried = (await conn.execute(text("SELECT bot_prs FROM repos WHERE id = 'r1'"))).scalar()
    assert carried == 7  # count preserved across the column rename


async def test_migration_error_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing migration propagates so startup aborts rather than serving a broken schema."""
    await apply_migrations()  # fresh → managed at head

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("migration exploded")

    monkeypatch.setattr(command, "upgrade", _boom)
    with pytest.raises(RuntimeError, match="migration exploded"):
        await apply_migrations()  # managed → upgrade head → boom must propagate
