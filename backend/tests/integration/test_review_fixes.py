"""Regression tests for code-review fixes:

* connection-scoped remediation overlay — a fix on one connection's repo must not
  bleed onto a same-named repo under another connection (composite-key correctness);
* mark-merged open-PR guard — merging a check with no open Hangar PR is rejected
  rather than fabricating a 'PR merged' pass + audit entry (FR-016 integrity);
* scorecard fail_count counts failures only (not unknown/pending) — honest state;
* the default auth-mode label comes from the adapter, not a provider branch in core.
"""

from __future__ import annotations

from hangar.domain.models import FindingStatus, ProviderConnection, RemediationState, Repo
from hangar.domain.policy import default_policy, effective_status
from hangar.persistence import repositories as repo_store
from hangar.services import connections as conn_service
from hangar.services.scorecard import build_scorecard


async def test_remediation_overlay_is_connection_scoped(session) -> None:
    repo_a = Repo(id="api", connection_id="conn-a", fails=["license"])
    repo_b = Repo(id="api", connection_id="conn-b", fails=["license"])

    # Open a fix on connection A's copy only.
    await repo_store.upsert_remediation(
        session, connection_id="conn-a", repo_id="api", check_id="license",
        kind="config_pr", state=RemediationState.pr_open.value, pr_url="http://x/1", pr_number=1,
    )
    rem = await repo_store.remediation_map(session)

    # A's copy shows the open PR; B's same-named repo is untouched (still failing).
    assert effective_status(repo_a, "license", rem) is FindingStatus.pending
    assert effective_status(repo_b, "license", rem) is FindingStatus.fail


def test_mark_merged_without_open_pr_returns_409(client) -> None:
    r = client.post("/api/v1/repos/hangar/checks/license/merge")
    assert r.status_code == 409, r.text


def test_mark_merged_after_open_pr_flips_to_fixed(client) -> None:
    opened = client.post("/api/v1/repos/hangar/checks/license/remediate", json={"kind": "config_pr"})
    assert opened.status_code == 200 and opened.json()["state"] == "pr_open"

    merged = client.post("/api/v1/repos/hangar/checks/license/merge")
    assert merged.status_code == 200, merged.text
    assert merged.json()["state"] == "fixed"


def test_scorecard_fail_count_excludes_unknown_and_pending() -> None:
    """`fail_count` is failures only — an `unknown` (undeterminable) repo must not be
    counted as a failure for that check."""
    policy = default_policy()
    conn = ProviderConnection(
        id="c1", label="gh:acme", provider_type="github", scope="org", auth_mode="App"
    )
    repos = [
        Repo(id="r1", connection_id="c1", fails=["license"], unknowns=[]),       # real fail
        Repo(id="r2", connection_id="c1", fails=[], unknowns=["license"]),       # unknown
        Repo(id="r3", connection_id="c1", fails=[], unknowns=[]),                # passing
    ]
    data = build_scorecard(repos, {"c1": conn}, policy, {})
    meta = {c["id"]: c for c in data["checks"]}
    assert meta["license"]["fail_count"] == 1  # only r1; r2 is unknown, not a fail


async def test_default_auth_mode_comes_from_adapter(session) -> None:
    """The default auth-mode label is supplied by the adapter (no `if provider == 'github'`
    branch in the provider-neutral connections service)."""
    gh = await conn_service.add_connection(
        session, provider_type="github", label="gh:auto", scope="org", credential="ghp_x"
    )
    assert gh.auth_mode == "GitHub App"
    gt = await conn_service.add_connection(
        session, provider_type="gitea", label="gitea:auto", scope="user", credential="tok"
    )
    assert gt.auth_mode == "Scoped token"
