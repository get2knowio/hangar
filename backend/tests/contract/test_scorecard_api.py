"""T037 — GET /fleet/scorecard contract."""

from __future__ import annotations


def test_scorecard_dimensions(client) -> None:
    body = client.get("/api/v1/fleet/scorecard").json()
    assert len(body["checks"]) == 31
    assert len(body["rows"]) == 14
    assert body["repo_count"] == 14
    assert "compliance_pct" in body
    assert isinstance(body["compliance_pct"], int)


def test_scorecard_rollup_top_drift_sorted_desc_capped(client) -> None:
    body = client.get("/api/v1/fleet/scorecard").json()
    rollup = body["rollup"]
    assert len(rollup) <= 4
    counts = [r["count"] for r in rollup]
    assert counts == sorted(counts, reverse=True)


def test_scorecard_unknown_cells_present_for_hangar_two_fa(client) -> None:
    body = client.get("/api/v1/fleet/scorecard").json()
    check_ids = [c["id"] for c in body["checks"]]
    two_fa_idx = check_ids.index("two_fa")
    rows = {row["repo_id"]: row for row in body["rows"]}
    assert rows["hangar"]["cells"][two_fa_idx] == "unknown"
    # some unknown cells exist across the matrix
    assert any("unknown" in row["cells"] for row in body["rows"])


def test_scorecard_failing_only_still_returns_rows(client) -> None:
    body = client.get("/api/v1/fleet/scorecard?failing_only=true").json()
    assert body["failing_only"] is True
    assert len(body["rows"]) == 14
    assert len(body["checks"]) == 31
