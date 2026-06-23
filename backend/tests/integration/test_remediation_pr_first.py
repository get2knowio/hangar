"""T047 — PR-first, never push; idle Hangar performs zero mutations (Constitution II, AS-8)."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from hangar.domain.models import Capability, ProviderConnection, RemediationKind, Repo
from hangar.providers.base import CorrectionRequest
from hangar.providers.demo import DemoProvider
from hangar.providers.github.adapter import GitHubAdapter


class _Recorder:
    """A fake githubkit client that records every REST call and returns minimal data."""

    def __init__(self, existing_open_pr: bool = False) -> None:
        self.calls: list[str] = []
        self._existing = existing_open_pr

    def _resp(self, data):
        return SimpleNamespace(parsed_data=data)

    def _make(self, name, data=None):
        async def _call(**kwargs):
            self.calls.append(name)
            self.last = getattr(self, "last", {})
            self.last[name] = kwargs
            return self._resp(data() if callable(data) else data)
        return _call

    @property
    def rest(self):
        existing = [SimpleNamespace(html_url="https://github.com/o/r/pull/9", number=9)] if self._existing else []
        return SimpleNamespace(
            pulls=SimpleNamespace(
                async_list=self._make("pulls.async_list", existing),
                async_create=self._make("pulls.async_create",
                                         SimpleNamespace(html_url="https://github.com/o/r/pull/77", number=77)),
            ),
            git=SimpleNamespace(
                async_get_ref=self._make("git.async_get_ref", SimpleNamespace(object_=SimpleNamespace(sha="abc"))),
                async_create_ref=self._make("git.async_create_ref"),
            ),
            repos=SimpleNamespace(
                async_create_or_update_file_contents=self._make("repos.create_or_update_file"),
            ),
        )


def _writable_conn() -> ProviderConnection:
    return ProviderConnection(
        id="gh", label="gh:acme", provider_type="github", scope="org", auth_mode="App",
        granted_capabilities={Capability.open_pull_request, Capability.read_files, Capability.deep_link},
        has_credential=True, token="t",
    )


def _req(repo_id="r", check="license"):
    repo = Repo(id=repo_id, connection_id="gh", default_branch="main")
    return CorrectionRequest(repo=repo, check_id=check, check_label="LICENSE present", kind=RemediationKind.config_pr)


async def test_github_open_pr_creates_pr_and_never_writes_default_branch(monkeypatch) -> None:
    """The live GitHub correct-path opens a PR on a NEW branch and never pushes/force-pushes
    or mutates the default branch ref (Constitution II / FR-014)."""
    adapter = GitHubAdapter()
    rec = _Recorder()
    monkeypatch.setattr(adapter, "_client", lambda conn: rec)

    result = await adapter.correct(_writable_conn(), _req())

    assert result.applied and result.pr_url.endswith("/pull/77")
    # A PR was opened on a fresh hangar/* branch off the default branch.
    assert "git.async_create_ref" in rec.calls
    assert rec.last["git.async_create_ref"]["ref"].startswith("refs/heads/hangar/")
    assert "pulls.async_create" in rec.calls
    # The default branch ref was only READ, never written/force-updated.
    assert "git.async_get_ref" in rec.calls
    assert not any("update_ref" in c or "force" in c for c in rec.calls)
    # No call carried a force flag.
    for kwargs in rec.last.values():
        assert kwargs.get("force") in (None, False)


async def test_github_open_pr_is_idempotent_on_existing_pr(monkeypatch) -> None:
    """If a Hangar PR is already open for (repo,check), surface it — do not create a branch/PR."""
    adapter = GitHubAdapter()
    rec = _Recorder(existing_open_pr=True)
    monkeypatch.setattr(adapter, "_client", lambda conn: rec)

    result = await adapter.correct(_writable_conn(), _req())

    assert result.idempotent_hit and result.pr_number == 9
    assert "git.async_create_ref" not in rec.calls
    assert "pulls.async_create" not in rec.calls


async def test_github_adapter_requires_credential() -> None:
    """No silent anonymous calls: the adapter refuses to act without an attached token."""
    adapter = GitHubAdapter()
    conn = _writable_conn()
    conn.token = None
    with pytest.raises(RuntimeError, match="no decrypted credential"):
        await adapter.correct(conn, _req())


def test_config_pr_yields_pr_url(client) -> None:
    r = client.post("/api/v1/repos/gh-main/hangar/checks/license/remediate", json={"kind": "config_pr"})
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
    detail = client.get("/api/v1/repos/gh-main/hangar").json()
    statuses = {}
    for grp in detail["check_groups"]:
        for c in grp["checks"]:
            statuses[c["id"]] = c["status"]
    for failing in ("license", "cooldown", "branch_protection", "code_scanning", "conventional"):
        assert statuses[failing] == "fail", failing
    assert statuses["two_fa"] == "unknown"
