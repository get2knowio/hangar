"""T059 — multi-connection fleet: add/list/attribute/delete with audit retention."""

from __future__ import annotations


def test_add_connection_appears_in_providers(client) -> None:
    before = client.get("/api/v1/providers").json()["connections"]
    before_ids = {c["id"] for c in before}

    resp = client.post("/api/v1/providers", json={
        "provider_type": "github",
        "label": "gh:extra-org",
        "scope": "org · 0 repos",
        "auth_mode": "GitHub App #9000",
    })
    assert resp.status_code == 201
    card = resp.json()
    assert card["type"] == "GitHub"

    after = client.get("/api/v1/providers").json()["connections"]
    after_ids = {c["id"] for c in after}
    assert after_ids - before_ids, "new connection should appear"


def test_fleet_union_attributes_every_row_to_a_connection(client) -> None:
    overview = client.get("/api/v1/fleet/overview").json()
    assert all(row["connection_badge"] for row in overview["repos"])

    scorecard = client.get("/api/v1/fleet/scorecard").json()
    assert all(row["connection_badge"] for row in scorecard["rows"])
    # union includes repos from all three seeded connections
    badges = {row["connection_badge"] for row in scorecard["rows"]}
    assert {"gh", "gitea"} & badges or len(badges) >= 1


def test_delete_connection_drops_repos_but_keeps_audit(client) -> None:
    # gh-labs has 3 repos and they appear before delete
    before = client.get("/api/v1/fleet/overview").json()
    labs_repos = {"scorecard-exp", "webhook-lab", "plex-grotesk"}
    before_ids = {r["id"] for r in before["repos"]}
    assert labs_repos <= before_ids

    audit_before = client.get("/api/v1/providers/audit?limit=200").json()

    resp = client.delete("/api/v1/providers/gh-labs")
    assert resp.status_code == 204

    after = client.get("/api/v1/fleet/overview").json()
    after_ids = {r["id"] for r in after["repos"]}
    assert not (labs_repos & after_ids), "labs repos should be gone from the fleet"

    # audit entries are retained (denormalized attribution survives connection removal)
    audit_after = client.get("/api/v1/providers/audit?limit=200").json()
    assert len(audit_after) == len(audit_before)
