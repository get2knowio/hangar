"""Fleet-wide (bulk) remediation — apply one check across many repos in one action."""

from __future__ import annotations


def _audit_pr_count(client) -> int:
    return len([e for e in client.get("/api/v1/providers/audit?limit=200").json()
                if "opened" in e["result"]])


def test_batch_opens_prs_and_collapses_readonly(client) -> None:
    body = {"targets": [
        {"connection_id": "gh-main", "repo_id": "hangar"},          # writable → PR
        {"connection_id": "gh-main", "repo_id": "conventional-bot"},  # writable → PR
        {"connection_id": "gitea", "repo_id": "backup-scripts"},     # read-only → deep-link
    ]}
    r = client.post("/api/v1/checks/license/remediate-batch", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    by = {(x["connection_id"], x["repo_id"]): x for x in data["results"]}

    assert by[("gh-main", "hangar")]["status"] == "pr_open"
    assert by[("gh-main", "hangar")]["pr_url"]
    assert by[("gh-main", "conventional-bot")]["status"] == "pr_open"
    # The read-only connection collapses the write to a deep-link, never a PR (FR-018).
    assert by[("gitea", "backup-scripts")]["status"] == "deep_link"
    assert by[("gitea", "backup-scripts")]["deep_link_url"]
    assert data["summary"].get("pr_open") == 2
    assert data["summary"].get("deep_link") == 1


def test_batch_writes_one_audit_entry_per_repo(client) -> None:
    before = _audit_pr_count(client)
    client.post("/api/v1/checks/license/remediate-batch", json={"targets": [
        {"connection_id": "gh-main", "repo_id": "hangar"},
        {"connection_id": "gh-main", "repo_id": "dotfiles"},
    ]})
    assert _audit_pr_count(client) == before + 2


def test_batch_is_idempotent(client) -> None:
    body = {"targets": [{"connection_id": "gh-main", "repo_id": "hangar"}]}
    first = client.post("/api/v1/checks/license/remediate-batch", json=body).json()
    assert first["results"][0]["status"] == "pr_open"
    assert first["results"][0]["idempotent_hit"] is False

    before = _audit_pr_count(client)
    second = client.post("/api/v1/checks/license/remediate-batch", json=body).json()
    assert second["results"][0]["status"] == "pr_open"
    assert second["results"][0]["idempotent_hit"] is True  # existing PR surfaced
    assert _audit_pr_count(client) == before  # no duplicate audit entry


def test_batch_isolates_unknown_targets(client) -> None:
    r = client.post("/api/v1/checks/license/remediate-batch", json={"targets": [
        {"connection_id": "gh-main", "repo_id": "hangar"},
        {"connection_id": "gh-main", "repo_id": "does-not-exist"},
        {"connection_id": "no-such-conn", "repo_id": "x"},
    ]})
    by = {(x["connection_id"], x["repo_id"]): x for x in r.json()["results"]}
    assert by[("gh-main", "hangar")]["status"] == "pr_open"       # unaffected by the bad targets
    assert by[("gh-main", "does-not-exist")]["status"] == "not_found"
    assert by[("no-such-conn", "x")]["status"] == "not_found"


def test_batch_unknown_check_is_404(client) -> None:
    r = client.post("/api/v1/checks/not-a-check/remediate-batch", json={"targets": []})
    assert r.status_code == 404
