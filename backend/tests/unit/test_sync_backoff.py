"""Regression: a connection whose discovery keeps failing is polled with exponential
backoff (not every cycle), an operator manual refresh bypasses that backoff, and the
scheduler job is guarded against overlapping itself."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from hangar.services import sync as syncmod
from hangar.services.sync import SyncService


class _DummyCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


def _service() -> SyncService:
    # sync_all only needs the sessionmaker to open a context; list_connections is patched.
    return SyncService(sessionmaker=lambda: _DummyCtx())


def test_backoff_grows_exponentially_then_resets() -> None:
    svc = _service()

    until1 = svc._record_failure("c1")
    until2 = svc._record_failure("c1")
    until3 = svc._record_failure("c1")
    assert svc._fail_streak["c1"] == 3

    now = datetime.now(UTC)
    d1 = (until1 - now).total_seconds()
    d2 = (until2 - now).total_seconds()
    d3 = (until3 - now).total_seconds()
    # Each window is ~double the previous (60 → 120 → 240); allow slack for clock drift.
    assert 50 < d1 < 70
    assert 110 < d2 < 130
    assert 230 < d3 < 250

    svc._record_success("c1")
    assert "c1" not in svc._fail_streak
    assert "c1" not in svc._backoff_until


def test_backoff_is_capped() -> None:
    svc = _service()
    for _ in range(20):
        until = svc._record_failure("c1")
    assert (until - datetime.now(UTC)).total_seconds() <= syncmod._BACKOFF_MAX_SECONDS + 5


async def test_sync_all_skips_connections_still_in_backoff(monkeypatch) -> None:
    svc = _service()

    async def fake_list(_session):
        return [SimpleNamespace(id="c1"), SimpleNamespace(id="c2")]

    monkeypatch.setattr(syncmod.repo, "list_connections", fake_list)

    called: list[str] = []

    async def fake_sync_connection(cid: str) -> int:
        called.append(cid)
        return 0

    svc.sync_connection = fake_sync_connection  # type: ignore[method-assign]
    # c1 is backed off into the future; c2 is eligible.
    svc._backoff_until["c1"] = datetime.now(UTC) + timedelta(seconds=300)

    await svc.sync_all()
    assert called == ["c2"]


async def test_sync_all_polls_once_backoff_expires(monkeypatch) -> None:
    svc = _service()

    async def fake_list(_session):
        return [SimpleNamespace(id="c1")]

    monkeypatch.setattr(syncmod.repo, "list_connections", fake_list)

    called: list[str] = []

    async def fake_sync_connection(cid: str) -> int:
        called.append(cid)
        return 0

    svc.sync_connection = fake_sync_connection  # type: ignore[method-assign]
    svc._backoff_until["c1"] = datetime.now(UTC) - timedelta(seconds=1)  # already expired

    await svc.sync_all()
    assert called == ["c1"]


async def test_scheduler_job_guards_against_overlap() -> None:
    svc = SyncService()
    svc.start()
    try:
        job = svc._scheduler.get_job("poll-all")
        assert job is not None
        assert job.max_instances == 1
        assert job.coalesce is True
    finally:
        svc.shutdown()
