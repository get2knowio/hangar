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
async def test_etag_304_returns_none_and_sends_if_none_match(respx_mock) -> None:
    pem = _rsa_pem()
    adapter = GitHubAdapter()
    conn = _app_connection(pem)
    # Seed the ETag store as if a prior poll had stored it.
    adapter._etags[("gh-main", "/repos/acme/hangar")] = '"v1"'

    repo_route, _ = _routes(respx_mock, httpx.Response(304, headers={"ETag": '"v1"'}))

    result = await adapter.interrogate(conn, "hangar")

    # 304 → snapshot unchanged; the poller keeps the cache.
    assert result is None
    # The conditional request really carried If-None-Match with the stored ETag.
    assert repo_route.called
    assert repo_route.calls.last.request.headers.get("if-none-match") == '"v1"'


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
