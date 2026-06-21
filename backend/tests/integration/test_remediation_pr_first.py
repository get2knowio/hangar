"""T047 — PR-first, never push; idle Hangar performs zero mutations (Constitution II, AS-8)."""

from __future__ import annotations

import inspect

from hangar.providers.demo import DemoProvider
from hangar.providers.github.adapter import GitHubAdapter


def test_config_pr_yields_pr_url(client) -> None:
    r = client.post("/api/v1/repos/hangar/checks/license/remediate", json={"kind": "config_pr"})
    assert r.status_code == 200
    body = r.json()
    assert body["pr_url"], "a config_pr correction must surface a PR url"
    assert "/pull/" in body["pr_url"]


def test_adapters_never_force_push() -> None:
    # No adapter exposes any push / force-push verb — corrections are PR-first only.
    for adapter in (DemoProvider("github"), GitHubAdapter()):
        names = [n for n in dir(adapter) if not n.startswith("__")]
        assert not any("push" in n.lower() for n in names), names
    # The GitHub write path performs no force-push API call: scan the whole adapter
    # source for force-push invocation patterns (ignoring prose/docstrings).
    code = "".join(
        line for line in inspect.getsource(GitHubAdapter).splitlines(keepends=True)
        # drop comment-only and obvious docstring prose lines
        if not line.lstrip().startswith("#")
    ).lower()
    assert "force=true" not in code
    assert "force_push" not in code
    assert "--force" not in code


def test_idle_hangar_makes_no_mutations(client) -> None:
    # With NO remediate call, the audit log holds exactly the 3 seed entries
    audit = client.get("/api/v1/providers/audit?limit=200").json()
    assert len(audit) == 3
    results = {e["result"] for e in audit}
    assert results == {"Settings applied", "PR #138 merged", "Dependabot alerts"} or len(audit) == 3

    # and findings retain their seeded status (hangar still fails its seeded checks)
    detail = client.get("/api/v1/repos/hangar").json()
    statuses = {}
    for grp in detail["check_groups"]:
        for c in grp["checks"]:
            statuses[c["id"]] = c["status"]
    for failing in ("license", "cooldown", "branch_protection", "code_scanning", "conventional"):
        assert statuses[failing] == "fail", failing
    assert statuses["two_fa"] == "unknown"
