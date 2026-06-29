"""Real GitHub integration tests (no demos): GitHub App installation-token minting and
genuine ETag conditional requests, driven through githubkit against a mocked HTTP API."""

from __future__ import annotations

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from hangar.domain.models import Capability, ProviderConnection, Repo
from hangar.providers.github.adapter import GitHubAdapter

API = "https://api.github.com"


def _rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _app_connection(pem: str) -> ProviderConnection:
    return ProviderConnection(
        id="gh-main", label="gh:acme", provider_type="github", scope="org",
        auth_mode="GitHub App #1", app_id="123", installation_id=456,
        granted_capabilities={
            Capability.read_files, Capability.read_settings,
            Capability.read_alerts, Capability.read_org_policy,
        },
        has_credential=True, token=pem,
    )


_REPO_JSON = {
    "name": "hangar", "default_branch": "main", "description": "Fleet control plane",
    "topics": ["homelab"], "license": {"spdx_id": "MIT"},
    "security_and_analysis": {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
    },
}


def _routes(mock: respx.MockRouter, repo_response: httpx.Response):
    """Register the live endpoints in priority order (specific first, catch-all last —
    respx is first-match-wins). Returns (repo_route, token_route) for assertions."""
    token_route = mock.post(url__regex=r".*/app/installations/\d+/access_tokens").mock(
        return_value=httpx.Response(
            201, json={"token": "ghs_installationtoken", "expires_at": "2999-01-01T00:00:00Z"}
        )
    )
    repo_route = mock.get(f"{API}/repos/acme/hangar").mock(return_value=repo_response)
    mock.get(url__regex=r".*/repos/acme/hangar/pulls.*").mock(return_value=httpx.Response(200, json=[]))
    mock.get(url__regex=r".*/repos/acme/hangar/actions/runs.*").mock(
        return_value=httpx.Response(200, json={"workflow_runs": []}))
    mock.get(url__regex=r".*/repos/acme/hangar/dependabot/alerts.*").mock(
        return_value=httpx.Response(200, json=[]))
    mock.get(f"{API}/orgs/acme").mock(
        return_value=httpx.Response(200, json={"two_factor_requirement_enabled": True}))
    # Everything else (contents/*, branches/*, code-scanning, workflow perms) → 404 absent.
    mock.route().mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
    return repo_route, token_route


@respx.mock(base_url=API, assert_all_called=False)
async def test_github_app_auth_mints_installation_token_and_interrogates(respx_mock) -> None:
    pem = _rsa_pem()
    adapter = GitHubAdapter()
    conn = _app_connection(pem)

    repo_route, token_route = _routes(
        respx_mock, httpx.Response(200, headers={"ETag": '"v1"'}, json=_REPO_JSON)
    )

    repo = await adapter.interrogate(conn, "hangar")

    # Real App auth happened: githubkit exchanged a signed JWT for an installation token.
    assert token_route.called, "GitHub App installation-token endpoint was not called"
    auth_header = token_route.calls.last.request.headers["authorization"]
    assert auth_header.startswith("Bearer "), "App JWT must be a Bearer token"

    # A real snapshot was built from live response JSON.
    assert repo is not None
    assert repo.default_branch == "main"
    assert "default_branch" not in repo.fails  # main → ok
    assert "license" not in repo.fails  # license present in metadata
    assert repo.license_spdx == "MIT"  # SPDX id captured for the finding evidence
    assert "secret_scanning" not in repo.fails  # enabled in security_and_analysis
    # Workflow checks are really evaluated (not blindly unknown): with no workflows dir,
    # dep_review/conventional fail and actions_pinned_sha passes vacuously (nothing to pin).
    assert "dep_review" in repo.fails
    assert "conventional" in repo.fails
    assert "actions_pinned_sha" not in repo.fails and "actions_pinned_sha" not in repo.unknowns

    # The conditional-request ETag was captured for next time.
    assert adapter._etags[("gh-main", "/repos/acme/hangar")] == '"v1"'
    assert repo_route.called


@respx.mock(base_url=API, assert_all_called=False)
async def test_etag_304_with_cached_snapshot_carries_forward_and_sends_if_none_match(
    respx_mock,
) -> None:
    pem = _rsa_pem()
    adapter = GitHubAdapter()
    conn = _app_connection(pem)
    # Seed the ETag store as if a prior poll had stored it.
    adapter._etags[("gh-main", "/repos/acme/hangar")] = '"v1"'

    repo_route, _ = _routes(respx_mock, httpx.Response(304, headers={"ETag": '"v1"'}))

    # The realistic 304 case: an ETag exists *because* a snapshot was cached, so `previous`
    # is supplied and its repo-body checks are carried forward (no refetch).
    previous = Repo(
        id="hangar", connection_id="gh-main", default_branch="main",
        description="Fleet control plane", fails=["license"], unknowns=[],
    )
    result = await adapter.interrogate(conn, "hangar", previous=previous)

    # 304 → repo body unchanged; the cached snapshot's checks carry forward.
    assert result is not None
    assert "license" in result.fails
    # The conditional request really carried If-None-Match with the stored ETag.
    assert repo_route.called
    assert repo_route.calls[0].request.headers.get("if-none-match") == '"v1"'


@respx.mock(base_url=API, assert_all_called=False)
async def test_token_auth_path_for_pat_connection(respx_mock) -> None:
    adapter = GitHubAdapter()
    conn = ProviderConnection(
        id="gh-pat", label="gh:acme", provider_type="github", scope="org",
        auth_mode="PAT", granted_capabilities={Capability.read_files},
        has_credential=True, token="ghp_pat",  # no app_id → TokenAuthStrategy
    )
    repo_route, _ = _routes(respx_mock, httpx.Response(200, headers={"ETag": '"v2"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    # PAT auth sends the token directly (no installation-token exchange).
    assert repo_route.calls.last.request.headers["authorization"] == "token ghp_pat"


@respx.mock(base_url=API, assert_all_called=False)
async def test_workflow_parsing_resolves_dep_review_conventional_and_pinned_sha(respx_mock) -> None:
    """Real .github/workflows parsing drives dep_review / conventional / actions_pinned_sha."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())

    workflow = (
        "name: ci\n"
        "on: [pull_request]\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4            # unpinned tag\n"
        "      - uses: actions/dependency-review-action@v4\n"
        "      - uses: wagoid/commitlint-github-action@b948419dd99f3fd78a6548d48f94e3df7f6bf3ed\n"
    )
    import base64 as _b64

    # Register the workflow routes BEFORE the catch-all (_routes adds the 404 last;
    # respx is first-match-wins).
    respx_mock.get(f"{API}/repos/acme/hangar/contents/.github/workflows").mock(
        return_value=httpx.Response(200, json=[
            {"name": "ci.yml", "path": ".github/workflows/ci.yml", "type": "file"},
        ])
    )
    respx_mock.get(f"{API}/repos/acme/hangar/contents/.github/workflows/ci.yml").mock(
        return_value=httpx.Response(200, json={
            "encoding": "base64", "content": _b64.b64encode(workflow.encode()).decode(),
        })
    )
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"w1"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    # dependency-review-action present → dep_review passes.
    assert "dep_review" not in repo.fails and "dep_review" not in repo.unknowns
    # commitlint action present → conventional passes.
    assert "conventional" not in repo.fails and "conventional" not in repo.unknowns
    # actions/checkout@v4 is a mutable tag → actions_pinned_sha fails.
    assert "actions_pinned_sha" in repo.fails


@respx.mock(base_url=API, assert_all_called=False)
async def test_release_health_from_release_and_head_dates(respx_mock) -> None:
    """release_pending_days = HEAD commit date − latest release date; release_health
    fails past the staleness threshold."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())

    # Register before the catch-all (respx first-match-wins).
    respx_mock.get(f"{API}/repos/acme/hangar/releases/latest").mock(
        return_value=httpx.Response(200, json={"published_at": "2024-01-01T00:00:00Z"})
    )
    respx_mock.get(f"{API}/repos/acme/hangar/commits/main").mock(
        return_value=httpx.Response(200, json={
            "commit": {"committer": {"date": "2024-01-21T00:00:00Z"}}  # 20 days later
        })
    )
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"r1"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert repo.release_pending_days == 20  # 20 unreleased days
    assert "release_health" in repo.fails  # ≥ 14-day threshold


@respx.mock(base_url=API, assert_all_called=False)
async def test_release_health_passes_when_head_at_release(respx_mock) -> None:
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    respx_mock.get(f"{API}/repos/acme/hangar/releases/latest").mock(
        return_value=httpx.Response(200, json={"published_at": "2024-01-21T00:00:00Z"})
    )
    respx_mock.get(f"{API}/repos/acme/hangar/commits/main").mock(
        return_value=httpx.Response(200, json={"commit": {"committer": {"date": "2024-01-21T00:00:00Z"}}})
    )
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"r2"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert repo.release_pending_days is None  # HEAD not ahead of the release
    assert "release_health" not in repo.fails


@respx.mock(base_url=API, assert_all_called=False)
async def test_304_with_previous_refreshes_volatile_signals(respx_mock) -> None:
    """A primary 304 reuses the prior snapshot's repo-body checks but STILL re-fetches
    volatile signals (alerts/CI/PRs/release) — a new critical alert must surface even
    though the repo resource is unchanged."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    adapter._etags[("gh-main", "/repos/acme/hangar")] = '"v1"'

    # A new critical Dependabot alert appears though the repo body is unchanged (304).
    # Distinct regex from _routes' alerts pattern so respx keeps both routes (it dedupes
    # identical patterns); registered first so first-match-wins picks the critical one.
    respx_mock.get(url__regex=r".*/dependabot/alerts(\?.*)?$").mock(
        return_value=httpx.Response(200, json=[{"security_advisory": {"severity": "critical"}}])
    )
    _routes(respx_mock, httpx.Response(304, headers={"ETag": '"v1"'}))

    previous = Repo(
        id="hangar", connection_id="gh-main", default_branch="main",
        description="Fleet control plane", fails=["license"], unknowns=[],
    )
    repo = await adapter.interrogate(conn, "hangar", previous=previous)

    assert repo is not None, "304 with a cached snapshot must still produce a snapshot"
    assert repo.alerts.critical == 1  # volatile signal refreshed despite the 304
    assert "license" in repo.fails  # repo-body check carried over from the previous snapshot


@respx.mock(base_url=API, assert_all_called=False)
async def test_403_on_subresource_yields_unknown_not_crash(respx_mock) -> None:
    """A 403 (e.g. Advanced Security disabled) maps the check to `unknown` and does NOT
    abort the whole snapshot (detection docstring contract)."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())

    respx_mock.get(f"{API}/repos/acme/hangar/code-scanning/analyses").mock(
        return_value=httpx.Response(403, json={"message": "Advanced Security disabled"})
    )
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"f1"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None  # the 403 did not propagate and abort interrogation
    assert "code_scanning" in repo.unknowns
    assert "code_scanning" not in repo.fails
    assert "default_branch" not in repo.fails  # the rest of the snapshot still evaluated


async def test_partial_app_config_fails_closed() -> None:
    """A half-configured App (app_id without installation_id) must NOT fall through to
    token auth and send the PEM as a bearer token — it fails closed."""
    adapter = GitHubAdapter()
    conn = ProviderConnection(
        id="gh-partial", label="gh:acme", provider_type="github", scope="org",
        auth_mode="App", app_id="123", installation_id=None,
        has_credential=True, token=_rsa_pem(),
    )
    with pytest.raises(RuntimeError, match="partial GitHub App"):
        await adapter.interrogate(conn, "hangar")


def test_has_unpinned_action_logic() -> None:
    from hangar.providers.github.detection import _has_unpinned_action

    assert _has_unpinned_action(["actions/checkout@v4"]) is True
    assert _has_unpinned_action(["actions/checkout@" + "a" * 40]) is False
    assert _has_unpinned_action(["./.github/actions/local", "docker://alpine:3"]) is False
    assert _has_unpinned_action(["owner/wf/.github/workflows/x.yml@v1"]) is True


async def test_adapter_refuses_without_credential() -> None:
    adapter = GitHubAdapter()
    conn = ProviderConnection(
        id="x", label="gh:acme", provider_type="github", scope="org", auth_mode="App",
        has_credential=True, token=None,
    )
    with pytest.raises(RuntimeError, match="no decrypted credential"):
        await adapter.interrogate(conn, "hangar")


# --- dependabot_alerts is really evaluated, never a fabricated pass (code-review fix) ---
@respx.mock(base_url=API, assert_all_called=False)
async def test_dependabot_alerts_enabled_passes(respx_mock) -> None:
    """vulnerability-alerts → 204 (enabled) ⇒ dependabot_alerts neither fails nor unknown."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    respx_mock.get(f"{API}/repos/acme/hangar/vulnerability-alerts").mock(
        return_value=httpx.Response(204)
    )
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"d1"'}, json=_REPO_JSON))
    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert "dependabot_alerts" not in repo.fails
    assert "dependabot_alerts" not in repo.unknowns


@respx.mock(base_url=API, assert_all_called=False)
async def test_dependabot_alerts_disabled_fails(respx_mock) -> None:
    """vulnerability-alerts → 404 (disabled) ⇒ a real fail, not the old silent pass."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    # _routes' catch-all returns 404 for vulnerability-alerts → disabled.
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"d2"'}, json=_REPO_JSON))
    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert "dependabot_alerts" in repo.fails


@respx.mock(base_url=API, assert_all_called=False)
async def test_dependabot_alerts_forbidden_is_unknown(respx_mock) -> None:
    """vulnerability-alerts → 403 ⇒ unknown (undeterminable), never fail/pass."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    respx_mock.get(f"{API}/repos/acme/hangar/vulnerability-alerts").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"d3"'}, json=_REPO_JSON))
    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert "dependabot_alerts" in repo.unknowns
    assert "dependabot_alerts" not in repo.fails


@respx.mock(base_url=API, assert_all_called=False)
async def test_dependabot_alerts_unknown_without_read_alerts(respx_mock) -> None:
    """No read_alerts capability ⇒ dependabot_alerts is unknown (capability-gated)."""
    adapter = GitHubAdapter()
    conn = ProviderConnection(
        id="gh-narrow", label="gh:acme", provider_type="github", scope="org",
        auth_mode="App", app_id="123", installation_id=456,
        granted_capabilities={Capability.read_files},  # no read_alerts
        has_credential=True, token=_rsa_pem(),
    )
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"d4"'}, json=_REPO_JSON))
    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert "dependabot_alerts" in repo.unknowns
    assert "dependabot_alerts" not in repo.fails


# --- list_repos degrades honestly on a forbidden listing (code-review fix) ---
def _pat_conn() -> ProviderConnection:
    return ProviderConnection(
        id="gh-pat", label="gh:acme", provider_type="github", scope="org",
        auth_mode="PAT", granted_capabilities={Capability.read_files},
        has_credential=True, token="ghp_pat",
    )


@respx.mock(base_url=API, assert_all_called=False)
async def test_list_repos_user_fallback_on_forbidden_org(respx_mock) -> None:
    """A 403 on the org listing falls back to the user endpoint."""
    adapter = GitHubAdapter()
    respx_mock.get(f"{API}/orgs/acme/repos").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"}))
    respx_mock.get(f"{API}/users/acme/repos").mock(
        return_value=httpx.Response(200, json=[{"name": "alpha"}, {"name": "beta"}]))
    assert await adapter.list_repos(_pat_conn()) == ["alpha", "beta"]


@respx.mock(base_url=API, assert_all_called=False)
async def test_list_repo_listings_reports_private_visibility(respx_mock) -> None:
    """list_repo_listings surfaces each repo's name + private flag for the picker padlock."""
    adapter = GitHubAdapter()
    respx_mock.get(f"{API}/orgs/acme/repos").mock(
        return_value=httpx.Response(200, json=[
            {"name": "secret-svc", "private": True},
            {"name": "open-docs", "private": False},
            {"name": "no-field"},  # absent ⇒ treated as public, not a guess
        ]))
    listings = await adapter.list_repo_listings(_pat_conn())
    assert {x.name: x.private for x in listings} == {
        "secret-svc": True, "open-docs": False, "no-field": False,
    }


@respx.mock(base_url=API, assert_all_called=False)
async def test_list_repos_raises_when_forbidden_everywhere(respx_mock) -> None:
    """403 on BOTH endpoints raises (undeterminable) so the poller keeps last-good
    snapshots instead of silently reporting an empty fleet."""
    adapter = GitHubAdapter()
    respx_mock.get(f"{API}/orgs/acme/repos").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"}))
    respx_mock.get(f"{API}/users/acme/repos").mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"}))
    with pytest.raises(RuntimeError, match="cannot list repos"):
        await adapter.list_repos(_pat_conn())


@respx.mock(base_url=API, assert_all_called=False)
async def test_pull_counts_paginate_beyond_one_page(respx_mock) -> None:
    """Open-PR counts paginate instead of silently capping at 100 (code-review fix)."""
    from urllib.parse import parse_qs, urlparse

    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())

    def _pulls(request: httpx.Request) -> httpx.Response:
        page = int(parse_qs(urlparse(str(request.url)).query).get("page", ["1"])[0])
        if page == 1:
            return httpx.Response(200, json=[{"user": {"login": "u"}}] * 100)
        if page == 2:
            return httpx.Response(200, json=[{"user": {"login": "u"}}] * 30)
        return httpx.Response(200, json=[])

    # Distinct regex from _routes' pulls pattern (respx dedupes identical patterns) and
    # registered first so first-match-wins picks the paginating mock.
    respx_mock.get(url__regex=r".*/repos/acme/hangar/pulls\?.*").mock(side_effect=_pulls)
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"p1"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert repo.open_prs == 130  # 100 (page 1) + 30 (page 2)


@respx.mock(base_url=API, assert_all_called=False)
async def test_open_prs_captured_into_snapshot(respx_mock) -> None:
    """The poller captures real open PRs (title/kind/url/draft) into the snapshot so the
    detail read can show them without a live call (open-PR interrogation feature)."""
    from urllib.parse import parse_qs, urlparse

    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())

    def _pulls(request: httpx.Request) -> httpx.Response:
        page = int(parse_qs(urlparse(str(request.url)).query).get("page", ["1"])[0])
        if page == 1:
            return httpx.Response(200, json=[
                {"title": "Bump vite", "number": 7, "html_url": "https://github.com/acme/hangar/pull/7",
                 "user": {"login": "dependabot[bot]"}, "created_at": "2024-01-01T00:00:00Z", "draft": False},
                {"title": "Add health", "number": 6, "html_url": "https://github.com/acme/hangar/pull/6",
                 "user": {"login": "alice"}, "created_at": "2024-01-02T00:00:00Z", "draft": True},
            ])
        return httpx.Response(200, json=[])

    respx_mock.get(url__regex=r".*/repos/acme/hangar/pulls\?.*").mock(side_effect=_pulls)
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"pr1"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert repo.open_prs == 2 and repo.bot_prs == 1
    assert [p.title for p in repo.pull_requests] == ["Bump vite", "Add health"]
    assert repo.pull_requests[0].kind == "dependabot"
    assert repo.pull_requests[0].url == "https://github.com/acme/hangar/pull/7"
    assert repo.pull_requests[1].kind == "human" and repo.pull_requests[1].draft is True


@respx.mock(base_url=API, assert_all_called=False)
async def test_secret_scanning_unknown_when_field_absent(respx_mock) -> None:
    """security_and_analysis omitted (token not repo-admin) ⇒ secret_scanning is unknown,
    not a fabricated fail (code-review fix)."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    repo_json = {k: v for k, v in _REPO_JSON.items() if k != "security_and_analysis"}
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"s1"'}, json=repo_json))
    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert "secret_scanning" in repo.unknowns
    assert "secret_scanning" not in repo.fails


@respx.mock(base_url=API, assert_all_called=False)
async def test_description_fails_on_missing_topics_with_honest_evidence(respx_mock) -> None:
    """A repo with a description but no topics fails the combined check, and the evidence
    does not falsely claim the description is empty (code-review fix)."""
    from hangar.domain.models import FindingStatus
    from hangar.domain.policy import evidence_for

    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    repo_json = {**_REPO_JSON, "topics": []}  # description present, no topics
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"t1"'}, json=repo_json))
    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert "description" in repo.fails
    assert evidence_for(repo, "description", FindingStatus.fail) == "Description or topics not set"


@respx.mock(base_url=API, assert_all_called=False)
async def test_license_evidence_shows_detected_spdx_id(respx_mock) -> None:
    """A passing license finding's evidence is the detected SPDX id, not a generic
    'Detected'. An unidentifiable license (GitHub NOASSERTION) has no id to show."""
    from hangar.domain.models import FindingStatus
    from hangar.domain.policy import evidence_for

    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())

    apache = {**_REPO_JSON, "license": {"spdx_id": "Apache-2.0"}}
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"lic1"'}, json=apache))
    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert repo.license_spdx == "Apache-2.0"
    assert evidence_for(repo, "license", FindingStatus.passing) == "Apache-2.0"

    # A LICENSE file GitHub can't map to a known id passes the check but yields no id.
    custom = {**_REPO_JSON, "license": {"spdx_id": "NOASSERTION"}}
    adapter2 = GitHubAdapter()
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"lic2"'}, json=custom))
    repo2 = await adapter2.interrogate(conn, "hangar")
    assert repo2 is not None
    assert "license" not in repo2.fails  # present → passes
    assert repo2.license_spdx is None
    assert evidence_for(repo2, "license", FindingStatus.passing) == "Detected"


@respx.mock(base_url=API, assert_all_called=False)
async def test_dependabot_alerts_use_cursor_pagination_not_page(respx_mock) -> None:
    """The dependabot alerts endpoint rejects ``?page=`` (400) and pages via an ``after``
    cursor in the Link header. Detection must follow the cursor and never send ``page=``
    (regression: a ``page=`` query 400'd and aborted the entire repo snapshot)."""
    from urllib.parse import parse_qs, urlparse

    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())

    def _alerts(request: httpx.Request) -> httpx.Response:
        q = parse_qs(urlparse(str(request.url)).query)
        # GitHub returns 400 here if ?page= is present; assert we never send it.
        assert "page" not in q, "must not send page= to the cursor-paginated alerts endpoint"
        after = q.get("after", [None])[0]
        if after is None:  # first page → Link points at the next cursor
            return httpx.Response(
                200,
                headers={"Link": f'<{API}/repos/acme/hangar/dependabot/alerts?after=CUR>; rel="next"'},
                json=[{"security_advisory": {"severity": "critical"}}],
            )
        if after == "CUR":  # second (last) page → no Link
            return httpx.Response(200, json=[{"security_advisory": {"severity": "high"}}])
        return httpx.Response(200, json=[])

    # Distinct regex from _routes' alerts pattern (respx dedupes identical patterns),
    # registered first so first-match-wins picks the cursor mock.
    respx_mock.get(url__regex=r".*/dependabot/alerts(\?.*)?$").mock(side_effect=_alerts)
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"a1"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None  # the endpoint no longer 400s the whole snapshot
    # Both cursor pages were aggregated (critical from page 1, high from page 2).
    assert repo.alerts.critical == 1
    assert repo.alerts.high == 1


@respx.mock(base_url=API, assert_all_called=False)
async def test_stale_etag_without_snapshot_refetches_in_full(respx_mock) -> None:
    """A 304 with no cached snapshot to carry forward (a stale in-memory ETag that outlived
    the row after the repo was pruned from an allowlist and re-added) must trigger a full
    refetch and rebuild — not leave the repo permanently absent (allowlist re-add
    regression)."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    # A stale ETag lingers from a prior poll though the snapshot row is gone.
    adapter._etags[("gh-main", "/repos/acme/hangar")] = '"stale"'

    calls = {"n": 0}

    def _repo(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.headers.get("if-none-match"):  # conditional probe → "unchanged"
            return httpx.Response(304, headers={"ETag": '"stale"'})
        return httpx.Response(200, headers={"ETag": '"fresh"'}, json=_REPO_JSON)  # full refetch

    # _routes registers the repo route + sub-resources; override the repo route afterwards
    # (same pattern → same respx Route) so it answers conditionally.
    _routes(respx_mock, httpx.Response(200, json=_REPO_JSON))
    respx_mock.get(f"{API}/repos/acme/hangar").mock(side_effect=_repo)

    repo = await adapter.interrogate(conn, "hangar", previous=None)

    assert repo is not None, "no previous snapshot must rebuild in full, not 304 to None"
    assert calls["n"] == 2, "expected a conditional 304 followed by a full refetch"
    assert repo.default_branch == "main"  # rebuilt from the full refetch body


@respx.mock(base_url=API, assert_all_called=False)
async def test_list_repos_empty_when_owner_not_found(respx_mock) -> None:
    """404 on org then user (no such owner) → empty list, not an error."""
    adapter = GitHubAdapter()
    respx_mock.get(f"{API}/orgs/acme/repos").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"}))
    respx_mock.get(f"{API}/users/acme/repos").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"}))
    assert await adapter.list_repos(_pat_conn()) == []


def _b64(text: str) -> dict:
    """A GitHub contents-API base64 payload (what _read_text decodes)."""
    import base64

    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


@respx.mock(base_url=API, assert_all_called=False)
async def test_renovate_pr_counts_as_bot_and_is_labeled_renovate(respx_mock) -> None:
    """A renovate[bot] PR is a dependency-bot PR (counted) and labelled 'renovate', not lumped
    under Dependabot (honest-state)."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    # Distinct regex from _routes' pulls pattern so respx keeps both (it dedupes by identical
    # pattern, and the later registration would otherwise win); added first → first-match wins.
    respx_mock.get(url__regex=r".*/repos/acme/hangar/pulls(\?.*)?$").mock(
        return_value=httpx.Response(200, json=[
            {"title": "Update vite", "number": 9, "html_url": "https://github.com/acme/hangar/pull/9",
             "user": {"login": "renovate[bot]"}, "created_at": "2026-06-01T00:00:00Z", "draft": False},
            {"title": "Bump black", "number": 8, "html_url": "https://github.com/acme/hangar/pull/8",
             "user": {"login": "dependabot[bot]"}, "created_at": "2026-06-02T00:00:00Z", "draft": False},
            {"title": "Refactor", "number": 7, "html_url": "https://github.com/acme/hangar/pull/7",
             "user": {"login": "octocat"}, "created_at": "2026-06-03T00:00:00Z", "draft": False},
        ]))
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"rn0"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert repo.open_prs == 3 and repo.bot_prs == 2  # renovate + dependabot, not the human
    kinds = {pr.title: pr.kind for pr in repo.pull_requests}
    assert kinds == {"Update vite": "renovate", "Bump black": "dependabot", "Refactor": "human"}


@respx.mock(base_url=API, assert_all_called=False)
async def test_renovate_config_satisfies_version_updates_and_cooldown(respx_mock) -> None:
    """A Renovate-only repo (no dependabot.yml) passes 'Version updates configured', and its
    minimumReleaseAge satisfies the cooldown check — no false failures for Renovate users."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    respx_mock.get(f"{API}/repos/acme/hangar/contents/renovate.json").mock(
        return_value=httpx.Response(200, json=_b64('{"minimumReleaseAge": "7 days"}')))
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"rn1"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert "dependabot_updates" not in repo.fails  # Renovate config counts as version updates
    assert "cooldown" not in repo.fails  # minimumReleaseAge present


@respx.mock(base_url=API, assert_all_called=False)
async def test_renovate_config_without_cooldown_fails_cooldown_only(respx_mock) -> None:
    """Renovate configured but with no minimumReleaseAge → version updates pass, cooldown fails."""
    adapter = GitHubAdapter()
    conn = _app_connection(_rsa_pem())
    respx_mock.get(f"{API}/repos/acme/hangar/contents/renovate.json").mock(
        return_value=httpx.Response(200, json=_b64('{"extends": ["config:recommended"]}')))
    _routes(respx_mock, httpx.Response(200, headers={"ETag": '"rn2"'}, json=_REPO_JSON))

    repo = await adapter.interrogate(conn, "hangar")
    assert repo is not None
    assert "dependabot_updates" not in repo.fails
    assert "cooldown" in repo.fails
