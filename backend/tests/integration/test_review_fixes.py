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
    r = client.post("/api/v1/repos/gh-main/hangar/checks/license/merge")
    assert r.status_code == 409, r.text


def test_mark_merged_after_open_pr_flips_to_fixed(client) -> None:
    opened = client.post(
        "/api/v1/repos/gh-main/hangar/checks/license/remediate", json={"kind": "config_pr"}
    )
    assert opened.status_code == 200 and opened.json()["state"] == "pr_open"

    merged = client.post("/api/v1/repos/gh-main/hangar/checks/license/merge")
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


async def test_get_repo_resolves_by_connection_not_id_alone(session) -> None:
    """A same-named repo under two connections resolves independently by
    (id, connection_id); the wrong connection never returns another's repo."""
    from hangar.persistence.models import ConnectionRow, RepoRow

    for cid in ("conn-a", "conn-b"):
        session.add(ConnectionRow(
            id=cid, label=f"gh:{cid}", provider_type="github", scope="org", auth_mode="App",
        ))
    session.add(RepoRow(id="api", connection_id="conn-a", description="A's api"))
    session.add(RepoRow(id="api", connection_id="conn-b", description="B's api"))
    await session.commit()

    a = await repo_store.get_repo(session, "api", "conn-a")
    b = await repo_store.get_repo(session, "api", "conn-b")
    assert a is not None and a.connection_id == "conn-a" and a.description == "A's api"
    assert b is not None and b.connection_id == "conn-b" and b.description == "B's api"
    # a connection that does not own 'api' gets nothing — never a silent wrong-connection pick
    assert await repo_store.get_repo(session, "api", "conn-c") is None


def test_repo_detail_route_is_connection_scoped(client) -> None:
    """The drill-in route is addressed by (connection_id, repo_id): the seeded `hangar`
    repo resolves under its owning connection and 404s under any other."""
    assert client.get("/api/v1/repos/gh-main/hangar").status_code == 200
    assert client.get("/api/v1/repos/gitea/hangar").status_code == 404


def test_repo_detail_checks_expose_structured_kind_and_pr_number(client) -> None:
    """Checks carry a structured remediation `kind` + `open_pr_number` so the UI never
    reverse-engineers them from a display label / PR URL (#4)."""
    detail = client.get("/api/v1/repos/gh-main/hangar").json()
    kinds = {"report", "deep_link", "settings_patch", "config_pr"}
    seen = False
    for grp in detail["check_groups"]:
        for c in grp["checks"]:
            seen = True
            assert c["kind"] in kinds
            assert "open_pr_number" in c
    assert seen, "expected at least one check"


def test_overview_tiles_expose_sub_tone(client) -> None:
    """Each stat tile carries a structured sub_tone so the UI colors subs without matching
    the tile label (#4)."""
    body = client.get("/api/v1/fleet/overview").json()
    assert body["stats"]
    for tile in body["stats"]:
        assert "sub_tone" in tile


async def test_connection_owner_persisted_and_overridable(session) -> None:
    """owner is a first-class field: derived from the label by default, or set explicitly
    for a label that doesn't follow the prefix:owner convention (#9)."""
    gh = await conn_service.add_connection(
        session, provider_type="github", label="gh:get2knowio", scope="org", credential="x"
    )
    assert gh.owner == "get2knowio"
    custom = await conn_service.add_connection(
        session, provider_type="github", label="prod", scope="org", credential="x",
        owner="acme-inc",
    )
    assert custom.owner == "acme-inc"


def test_empty_fleet_compliance_is_zero() -> None:
    """An empty fleet reports 0% compliance, not a misleading 100% (#9)."""
    from hangar.services.overview import build_overview
    from hangar.services.scorecard import build_scorecard

    policy = default_policy()
    assert build_overview([], {}, policy, {}, synced="never")["summary"]["compliance_pct"] == 0
    assert build_scorecard([], {}, policy, {})["compliance_pct"] == 0


def test_pr_list_not_fabricated_for_live_connections() -> None:
    """A live (credentialed) connection gets no fabricated PR rows; the demo-only path keeps
    the illustrative list and tags each row with a structured status_tone (#4, #9)."""
    from hangar.services.repo_detail import _pr_list

    repo = Repo(id="r", connection_id="c", open_prs=3, bot_prs=1)
    assert _pr_list(repo, synthesize=False) == []
    synthetic = _pr_list(repo, synthesize=True)
    assert len(synthetic) == 3 and all("status_tone" in p for p in synthetic)
