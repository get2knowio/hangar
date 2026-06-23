"""T048 — read-only connection collapses writes to deep-link (FR-018)."""

from __future__ import annotations


def test_config_pr_on_readonly_returns_403_with_deep_link(client) -> None:
    # backup-scripts is on the read-only gitea connection.
    r = client.post(
        "/api/v1/repos/gitea/backup-scripts/checks/license/remediate",
        json={"kind": "config_pr"},
    )
    assert r.status_code == 403
    body = r.json()
    assert body.get("deep_link_url"), body


def test_readonly_repo_detail_offers_only_deep_link_actions(client) -> None:
    detail = client.get("/api/v1/repos/gitea/backup-scripts").json()
    assert detail["read_only"] is True
    primary_actions = []
    for grp in detail["check_groups"]:
        for c in grp["checks"]:
            if c["status"] in ("fail", "unknown") and c["primary_action"]:
                primary_actions.append(c["primary_action"])
    assert primary_actions, "should have at least one actionable finding"
    # no write-style primary actions on a read-only connection
    for action in primary_actions:
        assert "Open fix PR" not in action
        assert action != "Enable"
        assert "Open in" in action  # deep-link only
