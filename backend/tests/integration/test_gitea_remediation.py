"""Gitea PR-first remediation against a mocked Gitea REST API.

A correction opens a pull request on a fresh ``hangar/<check>`` branch and never pushes or
force-pushes the default branch (Constitution II / FR-014); a second call for the same
(repo, check) surfaces the existing open PR instead of duplicating it (FR-015).
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from hangar.domain.models import Capability, ProviderConnection, RemediationKind, Repo
from hangar.providers.base import CorrectionRequest
from hangar.providers.gitea.adapter import GiteaAdapter

WEB = "https://gitea.example.com"
API = f"{WEB}/api/v1"


def _writable_conn() -> ProviderConnection:
    return ProviderConnection(
        id="gitea", label="gitea:acme", provider_type="gitea", scope="org",
        auth_mode="Scoped token", base_url=WEB, owner="acme",
        granted_capabilities={
            Capability.open_pull_request, Capability.read_files, Capability.deep_link,
        },
        has_credential=True, token="pat-secret",
    )


def _req(check: str = "license", label: str = "LICENSE present") -> CorrectionRequest:
    repo = Repo(id="hangar", connection_id="gitea", default_branch="main")
    return CorrectionRequest(
        repo=repo, check_id=check, check_label=label, kind=RemediationKind.config_pr
    )


def _write_routes(mock: respx.MockRouter, *, path: str):
    """Stub the create-branch / create-file / create-PR endpoints. Returns the routes."""
    branch = mock.post(f"{API}/repos/acme/hangar/branches").mock(
        return_value=httpx.Response(201, json={"name": "hangar/x"}))
    contents = mock.post(f"{API}/repos/acme/hangar/contents/{path}").mock(
        return_value=httpx.Response(201, json={"content": {"name": path}}))
    pull = mock.post(f"{API}/repos/acme/hangar/pulls").mock(
        return_value=httpx.Response(201, json={
            "number": 77, "html_url": f"{WEB}/acme/hangar/pulls/77"}))
    return branch, contents, pull


@respx.mock(base_url=API, assert_all_called=False)
async def test_config_pr_opens_branch_file_and_pr_on_feature_branch(respx_mock) -> None:
    respx_mock.get(url__regex=r".*/repos/acme/hangar/pulls(\?.*)?$").mock(
        return_value=httpx.Response(200, json=[]))
    branch, contents, pull = _write_routes(respx_mock, path="LICENSE")

    result = await GiteaAdapter().correct(_writable_conn(), _req())

    assert result.applied and not result.idempotent_hit
    assert result.pr_number == 77 and result.pr_url.endswith("/pulls/77")
    assert branch.called and contents.called and pull.called

    # The branch was cut from the default branch; the file landed on the FEATURE branch, never
    # the default — no push/force-push to main (Constitution II).
    assert json.loads(branch.calls.last.request.content) == {
        "new_branch_name": "hangar/license", "old_branch_name": "main"}
    assert json.loads(contents.calls.last.request.content)["branch"] == "hangar/license"
    pr_body = json.loads(pull.calls.last.request.content)
    assert pr_body["head"] == "hangar/license" and pr_body["base"] == "main"


@respx.mock(base_url=API, assert_all_called=False)
async def test_config_pr_is_idempotent_on_existing_open_pr(respx_mock) -> None:
    respx_mock.get(url__regex=r".*/repos/acme/hangar/pulls(\?.*)?$").mock(
        return_value=httpx.Response(200, json=[
            {"number": 9, "html_url": f"{WEB}/acme/hangar/pulls/9",
             "head": {"ref": "hangar/license"}}]))
    branch, _, pull = _write_routes(respx_mock, path="LICENSE")

    result = await GiteaAdapter().correct(_writable_conn(), _req())

    assert result.idempotent_hit and result.pr_number == 9
    # No duplicate branch or PR was created.
    assert not branch.called and not pull.called


@respx.mock(base_url=API, assert_all_called=False)
async def test_dependabot_updates_remediation_writes_renovate_config(respx_mock) -> None:
    # Gitea is a Renovate world: the update-bot remediation writes renovate.json, NOT a
    # GitHub-only .github/dependabot.yml — and that path is a detection candidate, so the PR
    # actually clears the finding.
    respx_mock.get(url__regex=r".*/repos/acme/hangar/pulls(\?.*)?$").mock(
        return_value=httpx.Response(200, json=[]))
    _, contents, _ = _write_routes(respx_mock, path="renovate.json")

    result = await GiteaAdapter().correct(
        _writable_conn(), _req("dependabot_updates", "Version updates configured"))

    assert result.applied and contents.called


async def test_correct_requires_credential() -> None:
    conn = _writable_conn()
    conn.token = None
    with pytest.raises(RuntimeError, match="no decrypted credential"):
        await GiteaAdapter().correct(conn, _req())


def test_gitea_adapter_exposes_no_push_verb() -> None:
    # Corrections are PR-first only — the adapter exposes no push/force-push method.
    names = [n for n in dir(GiteaAdapter()) if not n.startswith("__")]
    assert not any("push" in n.lower() for n in names), names
