"""Per-connection repo allowlist (FR-021–FR-026, Constitution I).

Selecting a subset scopes the connection's fleet, prunes de-selected snapshots, and stays
connection-scoped — a same-named repo on another connection is never touched. Driven
through the API against the seeded fixtures (offline demo provider, no network).
"""

from __future__ import annotations


def _card(client, conn_id: str) -> dict:
    cards = client.get("/api/v1/providers").json()["connections"]
    return next(c for c in cards if c["id"] == conn_id)


def test_allowlist_prunes_to_selection_and_is_connection_scoped(client) -> None:
    before_main = _card(client, "gh-main")["repos"]
    before_labs = _card(client, "gh-labs")["repos"]
    assert before_main >= 2 and before_labs >= 1  # seeded baseline

    # Scope gh-main down to a single repo.
    r = client.put("/api/v1/providers/gh-main/repos", json={"repos": ["hangar"]})
    assert r.status_code == 200
    card = r.json()
    assert card["repo_allowlist"] == ["hangar"]
    assert card["repos"] == 1  # de-selected snapshots pruned immediately

    # The other connection's repos are untouched (prune is scoped to gh-main).
    assert _card(client, "gh-labs")["repos"] == before_labs

    # The surviving repo is exactly the selected one, and the picker reflects the state.
    repos = client.get("/api/v1/providers/gh-main/repos").json()
    assert repos["selected"] == ["hangar"]
    assert repos["watching_all"] is False


def test_default_connection_watches_all(client) -> None:
    repos = client.get("/api/v1/providers/gh-main/repos").json()
    assert repos["watching_all"] is True
    assert repos["selected"] is None


def test_clearing_the_allowlist_returns_to_watch_all(client) -> None:
    client.put("/api/v1/providers/gh-main/repos", json={"repos": ["hangar"]})
    card = client.put("/api/v1/providers/gh-main/repos", json={"repos": None}).json()
    assert card["repo_allowlist"] is None


def test_empty_selection_normalizes_to_watch_all(client) -> None:
    # Deselecting everything means "no filter" (watch all), not "watch nothing".
    card = client.put("/api/v1/providers/gh-main/repos", json={"repos": []}).json()
    assert card["repo_allowlist"] is None


def test_set_repos_on_unknown_connection_is_404(client) -> None:
    r = client.put("/api/v1/providers/does-not-exist/repos", json={"repos": ["x"]})
    assert r.status_code == 404
