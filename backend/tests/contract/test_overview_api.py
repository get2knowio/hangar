"""T027 — GET /fleet/overview contract."""

from __future__ import annotations


def test_overview_stat_tiles_order(client) -> None:
    r = client.get("/api/v1/fleet/overview")
    assert r.status_code == 200
    body = r.json()
    labels = [s["label"] for s in body["stats"]]
    assert labels == [
        "Open PRs", "Bot PRs", "CI failing", "Sec alerts", "Release pending", "Compliance",
    ]


def test_overview_repo_rows_carry_connection_badge_and_dependabot(client) -> None:
    body = client.get("/api/v1/fleet/overview").json()
    assert body["summary"]["repo_count"] == 14
    rows = {row["id"]: row for row in body["repos"]}
    # every row attributed to a connection badge
    assert all(row["connection_badge"] for row in body["repos"])
    # hangar has 3 dependabot PRs in the seed
    assert rows["hangar"]["dependabot_prs"] == 3
    assert "dependabot_prs" in rows["hangar"]


def test_overview_feed_urgency_ordered_hangar_critical_first(client) -> None:
    body = client.get("/api/v1/fleet/overview").json()
    feed = body["feed"]
    assert feed, "feed should not be empty"
    first = feed[0]
    assert first["tag"] == "Critical"
    assert first["repo_id"] == "hangar"


def test_overview_connection_filter_rescopes(client) -> None:
    all_body = client.get("/api/v1/fleet/overview").json()
    labs = client.get("/api/v1/fleet/overview?connection=gh-labs").json()
    assert labs["summary"]["repo_count"] < all_body["summary"]["repo_count"]
    # gh-labs has 3 repos in the seed
    assert labs["summary"]["repo_count"] == 3
    badges = {row["connection_badge"] for row in labs["repos"]}
    assert badges == {"get2know-labs"}
