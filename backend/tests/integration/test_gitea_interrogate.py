"""Real Gitea interrogation against a mocked Gitea REST API (no demo simulator).

Exercises the read path end to end: a normalized snapshot built from live Gitea JSON,
GitHub-only signals reported as honest ``unknown`` (never a fabricated fail), absolute
deep-links/PR URLs derived from the connection's self-hosted ``base_url``, and the
org→user repo-listing fallback.
"""

from __future__ import annotations

import base64

import httpx
import respx

from hangar.domain.models import Capability, CIStatus, ProviderConnection, Repo
from hangar.providers.gitea.adapter import GiteaAdapter


def _contents_b64(text: str) -> httpx.Response:
    """A Gitea contents-API response carrying base64 file content (as _read_text expects)."""
    return httpx.Response(200, json={
        "type": "file", "encoding": "base64",
        "content": base64.b64encode(text.encode()).decode(),
    })

WEB = "https://gitea.example.com"
API = f"{WEB}/api/v1"

# Signals OSS Gitea has no API for — must be unknown, never fail (Constitution VIII).
_GITHUB_ONLY = {
    "dependabot_alerts", "secret_scanning", "code_scanning", "workflow_permissions", "two_fa",
}


def _connection() -> ProviderConnection:
    return ProviderConnection(
        id="gitea-main", label="gitea:acme", provider_type="gitea", scope="org",
        auth_mode="Scoped token", base_url=WEB, owner="acme",
        granted_capabilities={
            Capability.read_settings, Capability.read_files, Capability.deep_link,
        },
        has_credential=True, token="pat-secret",
    )


_REPO_JSON = {"name": "hangar", "default_branch": "main", "description": "Fleet control plane"}


def _present_file_routes(mock: respx.MockRouter) -> None:
    """Files that exist (everything else under contents/ falls through to the catch-all 404)."""
    for path in ("LICENSE", "README.md"):
        mock.get(f"{API}/repos/acme/hangar/contents/{path}").mock(
            return_value=httpx.Response(200, json={"name": path, "type": "file"})
        )


def _routes(mock: respx.MockRouter, *, protection: httpx.Response) -> None:
    """Register Gitea endpoints (specific first, catch-all 404 last — first-match-wins)."""
    mock.get(f"{API}/repos/acme/hangar").mock(return_value=httpx.Response(200, json=_REPO_JSON))
    mock.get(f"{API}/repos/acme/hangar/topics").mock(
        return_value=httpx.Response(200, json={"topics": ["homelab"]}))
    mock.get(f"{API}/repos/acme/hangar/branch_protections/main").mock(return_value=protection)
    mock.get(url__regex=r".*/repos/acme/hangar/pulls(\?.*)?$").mock(
        return_value=httpx.Response(200, json=[
            {"number": 7, "title": "Update deps", "html_url": f"{WEB}/acme/hangar/pulls/7",
             "user": {"login": "renovate[bot]"}, "created_at": "2026-01-02T00:00:00Z",
             "draft": False},
            {"number": 6, "title": "Add feature", "html_url": f"{WEB}/acme/hangar/pulls/6",
             "user": {"login": "octocat"}, "created_at": "2026-01-01T00:00:00Z", "draft": False},
        ]))
    mock.get(f"{API}/repos/acme/hangar/commits/main/status").mock(
        return_value=httpx.Response(200, json={"state": "success"}))
    _present_file_routes(mock)
    # Everything else (other contents, workflows dirs, releases/latest) → 404 absent.
    mock.route().mock(return_value=httpx.Response(404, json={"message": "Not Found"}))


@respx.mock(base_url=API, assert_all_called=False)
async def test_interrogate_builds_real_snapshot_and_marks_github_only_unknown(respx_mock) -> None:
    _routes(respx_mock, protection=httpx.Response(200, json={"branch_name": "main"}))

    repo = await GiteaAdapter().interrogate(_connection(), "hangar")

    assert repo is not None
    # Built from live JSON, not carried/fabricated.
    assert repo.default_branch == "main" and "default_branch" not in repo.fails
    assert repo.description == "Fleet control plane"

    # File-presence checks really evaluated: present passes, absent fails.
    assert "license" not in repo.fails       # LICENSE present
    assert "readme" not in repo.fails        # README.md present
    assert "security_md" in repo.fails       # absent → fail
    assert repo.license_spdx is None         # Gitea has no SPDX id to surface

    # Settings + metadata + workflow checks.
    assert "branch_protection" not in repo.fails     # protection present
    assert "description" not in repo.fails            # description + topics both set
    assert "dep_review" in repo.fails and "conventional" in repo.fails  # no workflows
    assert "actions_pinned_sha" not in repo.fails     # nothing to pin → vacuously ok

    # CI from the combined commit status.
    assert repo.ci_status is CIStatus.passing
    assert "ci_workflow_green" not in repo.fails and "ci_workflow_green" not in repo.unknowns

    # Pulls + bot classification (Renovate counts as a dependency bot).
    assert repo.open_prs == 2 and repo.bot_prs == 1
    assert {p.kind for p in repo.pull_requests} == {"renovate", "human"}

    # Every GitHub-only signal is unknown, and none of them leaked into fails.
    assert _GITHUB_ONLY <= set(repo.unknowns)
    assert _GITHUB_ONLY.isdisjoint(repo.fails)


@respx.mock(base_url=API, assert_all_called=False)
async def test_added_checks_detected_cheaply_or_honest_unknown(respx_mock) -> None:
    """The best-practice additions are detected on Gitea where the reads are already made
    (contributing, dangerous_workflow, ci_tests_on_pr, sbom, signed_releases, pinned_deps),
    and honestly ``unknown`` where the deferred adapter doesn't wire the read yet
    (binary_artifacts, signed_commits) — never a fabricated pass."""
    workflow = (
        "on: [pull_request]\njobs:\n  b:\n    steps:\n"
        "      - uses: anchore/sbom-action@v0\n"
        "      - uses: sigstore/cosign-installer@v3\n"
        "      - run: echo ok\n"
    )
    respx_mock.get(f"{API}/repos/acme/hangar/contents/.gitea/workflows").mock(
        return_value=httpx.Response(200, json=[
            {"name": "ci.yml", "path": ".gitea/workflows/ci.yml", "type": "file"}]))
    respx_mock.get(f"{API}/repos/acme/hangar/contents/.gitea/workflows/ci.yml").mock(
        return_value=_contents_b64(workflow))
    respx_mock.get(f"{API}/repos/acme/hangar/contents/CONTRIBUTING.md").mock(
        return_value=httpx.Response(200, json={"name": "CONTRIBUTING.md", "type": "file"}))
    respx_mock.get(f"{API}/repos/acme/hangar/contents/Dockerfile").mock(
        return_value=_contents_b64("FROM python@sha256:" + "a" * 64 + "\n"))
    _routes(respx_mock, protection=httpx.Response(200, json={"branch_name": "main"}))

    repo = await GiteaAdapter().interrogate(_connection(), "hangar")
    assert repo is not None
    for cid in ("contributing", "dangerous_workflow", "ci_tests_on_pr",
                "sbom", "signed_releases", "pinned_deps"):
        assert cid not in repo.fails and cid not in repo.unknowns, cid
    for cid in ("binary_artifacts", "signed_commits"):
        assert cid in repo.unknowns and cid not in repo.fails, cid


@respx.mock(base_url=API, assert_all_called=False)
async def test_forbidden_resource_degrades_to_unknown_not_fail(respx_mock) -> None:
    # A 403 on branch protection means "can't determine", not "not configured".
    _routes(respx_mock, protection=httpx.Response(403, json={"message": "Forbidden"}))

    repo = await GiteaAdapter().interrogate(_connection(), "hangar")

    assert repo is not None
    assert "branch_protection" in repo.unknowns
    assert "branch_protection" not in repo.fails


@respx.mock(base_url=API, assert_all_called=False)
async def test_unreadable_repo_returns_none(respx_mock) -> None:
    respx_mock.get(f"{API}/repos/acme/ghost").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"}))
    respx_mock.route().mock(return_value=httpx.Response(404))

    assert await GiteaAdapter().interrogate(_connection(), "ghost") is None


@respx.mock(base_url=API, assert_all_called=False)
async def test_list_repos_falls_back_from_org_to_user(respx_mock) -> None:
    respx_mock.get(f"{API}/orgs/acme/repos").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"}))
    respx_mock.get(f"{API}/users/acme/repos").mock(return_value=httpx.Response(200, json=[
        {"name": "hangar", "private": False}, {"name": "secret-svc", "private": True},
    ]))

    adapter = GiteaAdapter()
    assert await adapter.list_repos(_connection()) == ["hangar", "secret-svc"]
    listings = await adapter.list_repo_listings(_connection())
    assert {r.name: r.private for r in listings} == {"hangar": False, "secret-svc": True}


@respx.mock(base_url=API, assert_all_called=False)
async def test_hangar_json_populates_suppressions(respx_mock) -> None:
    respx_mock.get(f"{API}/repos/acme/hangar/contents/.hangar.json").mock(
        return_value=_contents_b64(
            '{"ignore": [{"check": "dependabot_alerts", "reason": "no deps"}, "code_scanning"]}'
        ))
    _routes(respx_mock, protection=httpx.Response(200, json={"branch_name": "main"}))

    repo = await GiteaAdapter().interrogate(_connection(), "hangar")

    assert repo is not None
    assert repo.suppressions == {"dependabot_alerts": "no deps", "code_scanning": ""}


@respx.mock(base_url=API, assert_all_called=False)
async def test_absent_hangar_json_leaves_suppressions_empty(respx_mock) -> None:
    # No .hangar.json route → catch-all 404; suppressions stay empty (no crash).
    _routes(respx_mock, protection=httpx.Response(200, json={"branch_name": "main"}))

    repo = await GiteaAdapter().interrogate(_connection(), "hangar")

    assert repo is not None
    assert repo.suppressions == {}


@respx.mock(base_url=API, assert_all_called=False)
async def test_malformed_hangar_json_is_ignored_not_fatal(respx_mock) -> None:
    respx_mock.get(f"{API}/repos/acme/hangar/contents/.hangar.json").mock(
        return_value=_contents_b64("{ this is not valid json"))
    _routes(respx_mock, protection=httpx.Response(200, json={"branch_name": "main"}))

    repo = await GiteaAdapter().interrogate(_connection(), "hangar")

    # Malformed config is fail-safe: no suppressions, snapshot still built.
    assert repo is not None
    assert repo.suppressions == {}


def test_deep_link_and_pr_url_are_absolute_instance_urls() -> None:
    adapter = GiteaAdapter()
    conn = _connection()
    repo = Repo(id="hangar", connection_id="gitea-main")
    assert adapter.deep_link(conn, repo, "branch_protection") == (
        f"{WEB}/acme/hangar/settings/branches"
    )
    assert adapter.deep_link(conn, repo, "readme") == f"{WEB}/acme/hangar"
    assert adapter.pr_url(conn, repo, 7) == f"{WEB}/acme/hangar/pulls/7"
