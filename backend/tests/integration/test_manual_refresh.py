"""Operator-triggered manual refresh (FR-033).

POST /providers/sync and /providers/{id}/sync enqueue an immediate background
re-interrogation on the same path as the scheduled poll. Driven through the API
against the seeded fixtures (offline demo provider, no network). The SyncService
methods are spied so the assertions are deterministic — TestClient runs the
background task after the response, so the spy has fired by the time we assert.
"""

from __future__ import annotations


def test_connection_sync_returns_202_and_triggers_that_connection(client) -> None:
    calls: list[str] = []

    async def fake_sync_connection(connection_id: str) -> int:
        calls.append(connection_id)
        return 0

    client.app.state.sync.sync_connection = fake_sync_connection

    r = client.post("/api/v1/providers/gh-main/sync")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert body["connection_id"] == "gh-main"
    # Background task fired with exactly this connection (scoped, not the whole fleet).
    assert calls == ["gh-main"]


def test_fleet_sync_returns_202_and_triggers_sync_all(client) -> None:
    calls: list[str] = []

    async def fake_sync_all() -> int:
        calls.append("all")
        return 0

    client.app.state.sync.sync_all = fake_sync_all

    r = client.post("/api/v1/providers/sync")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert body["connection_id"] is None
    assert calls == ["all"]


def test_sync_unknown_connection_is_404_and_triggers_nothing(client) -> None:
    calls: list[str] = []

    async def fake_sync_connection(connection_id: str) -> int:  # pragma: no cover - must not run
        calls.append(connection_id)
        return 0

    client.app.state.sync.sync_connection = fake_sync_connection

    r = client.post("/api/v1/providers/does-not-exist/sync")
    assert r.status_code == 404
    assert calls == []
