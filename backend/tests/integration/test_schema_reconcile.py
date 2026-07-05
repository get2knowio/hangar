"""Startup schema reconciliation (the 0.3.4→0.3.8 outage regression).

An in-place image upgrade that added a column to a pre-existing table (PR #45 added
``repos.suppressions``) left that column missing, because the container only ran
``create_all`` — which creates absent tables but never alters existing ones. Every query
that selected the table then failed with ``no such column: repos.suppressions`` → 500s
across the whole API. ``ensure_schema`` reconciles missing columns so the upgrade heals
itself on the next start.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from hangar.persistence.db import create_all, ensure_schema, get_engine, reset_engine


async def _columns(table: str) -> set[str]:
    engine = get_engine()
    async with engine.connect() as conn:
        return set(
            await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns(table)})
        )


async def test_ensure_schema_readds_a_column_create_all_would_miss() -> None:
    # Build the current schema, then simulate an older DB by dropping a column a later
    # release added — exactly the drift an in-place upgrade produces.
    await create_all()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE repos DROP COLUMN suppressions"))
    assert "suppressions" not in await _columns("repos")

    # create_all alone leaves the existing table untouched — the column stays missing.
    await create_all()
    assert "suppressions" not in await _columns("repos")

    # ensure_schema reconciles it (additive, nullable-safe), and is idempotent on re-run.
    await ensure_schema()
    assert "suppressions" in await _columns("repos")
    await ensure_schema()
    assert "suppressions" in await _columns("repos")


async def test_ensure_schema_reconciled_column_is_queryable() -> None:
    """After reconciliation a SELECT of the previously-missing column succeeds (the 500 path)."""
    await create_all()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE repos DROP COLUMN suppressions"))

    # The exact failure the outage hit: selecting the column errors before reconciliation.
    with pytest.raises(OperationalError):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT suppressions FROM repos"))

    await ensure_schema()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT suppressions FROM repos"))  # no error


async def test_fleet_overview_heals_on_startup() -> None:
    """End-to-end reproduction: a DB drifted like the production one serves 200s after start.

    Build the schema, drop the release-added column (the exact pre-upgrade state), then boot
    the app — its lifespan runs ensure_schema, which must reconcile the column so the fleet
    read path that 500'd in production returns 200 again."""
    await create_all()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE repos DROP COLUMN suppressions"))
    # Drop the engine so the app opens a fresh one against the same (drifted) DB file.
    await reset_engine()

    from hangar.main import create_app

    with TestClient(create_app()) as c:  # lifespan → ensure_schema + seed
        r = c.get("/api/v1/fleet/overview")
    assert r.status_code == 200
