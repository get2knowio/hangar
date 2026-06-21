"""T046 — config_pr remediation is idempotent (FR-015)."""

from __future__ import annotations


def _audit_pr_entries(client) -> list[dict]:
    entries = client.get("/api/v1/providers/audit?limit=200").json()
    return [e for e in entries if "opened" in e["result"]]


def test_config_pr_idempotent_same_pr_url_single_audit(client) -> None:
    url = "/api/v1/repos/hangar/checks/license/remediate"

    before = len(_audit_pr_entries(client))

    r1 = client.post(url, json={"kind": "config_pr"})
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["state"] == "pr_open"
    assert b1["idempotent_hit"] is False
    assert b1["pr_url"]

    # one new "PR ... opened" audit entry
    after_first = _audit_pr_entries(client)
    assert len(after_first) == before + 1

    # re-trigger the same correction
    r2 = client.post(url, json={"kind": "config_pr"})
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["state"] == "pr_open"
    assert b2["idempotent_hit"] is True
    assert b2["pr_url"] == b1["pr_url"]

    # NO duplicate audit entry was appended
    after_second = _audit_pr_entries(client)
    assert len(after_second) == before + 1
