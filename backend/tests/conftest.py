"""Shared pytest fixtures for the Hangar backend test suite.

Each test gets a fresh, seeded SQLite database in a temp file. The required
fail-closed env vars (``HANGAR_FORWARD_AUTH``, ``HANGAR_SECRET_KEY``,
``HANGAR_DATABASE_URL``) are set per-test via monkeypatch so the app factory's
startup gate is satisfied. The engine/sessionmaker singletons are reset between
tests so each gets its own DB.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from hangar.config import Settings, set_settings
from hangar.persistence.db import get_sessionmaker, reset_engine

# A single Fernet key reused across the session keeps credential round-trips stable.
_FERNET_KEY = Fernet.generate_key().decode()


def _run_sync(coro) -> None:
    """Run a coroutine to completion from sync fixture/test code.

    On Python 3.12+ ``asyncio.get_event_loop()`` no longer implicitly creates a
    loop, so use a fresh loop explicitly.
    """
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path) -> Iterator[None]:
    """Set required env, re-read settings, and reset the DB engine per test."""
    db_path = tmp_path / "hangar-test.db"
    monkeypatch.setenv("HANGAR_FORWARD_AUTH", "disabled")
    monkeypatch.setenv("HANGAR_SECRET_KEY", _FERNET_KEY)
    monkeypatch.setenv("HANGAR_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("HANGAR_SEED_DEMO_DATA", "true")
    # Loopback bind + no public-bind so validate_startup never trips the bind gate.
    monkeypatch.setenv("HANGAR_HOST", "127.0.0.1")
    monkeypatch.delenv("HANGAR_TRUSTED_PROXY_CIDR", raising=False)
    monkeypatch.delenv("HANGAR_TRUSTED_PROXY_SECRET", raising=False)
    monkeypatch.delenv("HANGAR_FORWARD_AUTH_ALLOWED_USER", raising=False)
    # Clear any inherited Postgres selection so the per-test SQLite URL above wins —
    # get_engine() resolves via effective_database_url, which HANGAR_POSTGRES_HOST
    # would otherwise override (pointing the suite at a real/absent Postgres).
    for _pg in ("HOST", "PORT", "DB", "USER", "PASSWORD", "SSLMODE"):
        monkeypatch.delenv(f"HANGAR_POSTGRES_{_pg}", raising=False)

    set_settings(Settings())
    _run_sync(reset_engine())
    yield
    _run_sync(reset_engine())


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient bound to a fresh app (runs lifespan → seeds the DB)."""
    from hangar.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
async def session() -> AsyncIterator:
    """An async session against the (already-created) per-test DB.

    Note: use the ``client`` fixture first if you need the seeded fixtures; the
    lifespan is what runs ``create_all`` + seed.
    """
    from hangar.persistence.db import create_all

    await create_all()
    sm = get_sessionmaker()
    async with sm() as s:
        yield s
