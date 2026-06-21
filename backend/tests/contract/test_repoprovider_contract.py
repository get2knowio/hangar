"""T020 — RepoProvider contract test, parametrized over every adapter.

Each adapter must satisfy the ``RepoProvider`` Protocol shape: a ``provider_type``
attribute, ``declared_capabilities()`` returning a ``set``, and the async verbs
``interrogate``/``list_repos``/``correct``/``subscribe`` plus the sync ``deep_link``.
DemoProvider's correct/interrogate/deep_link shapes are exercised concretely.
"""

from __future__ import annotations

import inspect

import pytest

from hangar.domain.models import (
    Capability,
    ProviderConnection,
    RemediationKind,
    Repo,
)
from hangar.providers.base import CorrectionRequest, CorrectionResult, RepoProvider
from hangar.providers.demo import DemoProvider
from hangar.providers.gitea.adapter import GiteaAdapter
from hangar.providers.github.adapter import GitHubAdapter

ADAPTERS = [
    DemoProvider("github"),
    DemoProvider("gitea"),
    GiteaAdapter(),
    GitHubAdapter(),
]


@pytest.mark.parametrize("adapter", ADAPTERS, ids=lambda a: f"{type(a).__name__}-{a.provider_type}")
def test_adapter_satisfies_protocol(adapter) -> None:
    # runtime_checkable Protocol: structural check.
    assert isinstance(adapter, RepoProvider)
    assert isinstance(adapter.provider_type, str) and adapter.provider_type


@pytest.mark.parametrize("adapter", ADAPTERS, ids=lambda a: type(a).__name__ + a.provider_type)
def test_declared_capabilities_is_a_set(adapter) -> None:
    caps = adapter.declared_capabilities()
    assert isinstance(caps, set)
    assert all(isinstance(c, Capability) for c in caps)


@pytest.mark.parametrize("adapter", ADAPTERS, ids=lambda a: type(a).__name__ + a.provider_type)
def test_async_methods_exist_and_are_coroutines(adapter) -> None:
    for name in ("interrogate", "list_repos", "correct", "subscribe"):
        assert hasattr(adapter, name)
        assert inspect.iscoroutinefunction(getattr(adapter, name)), name
    # deep_link is sync.
    assert hasattr(adapter, "deep_link")
    assert not inspect.iscoroutinefunction(adapter.deep_link)


@pytest.fixture
def demo_connection() -> ProviderConnection:
    return ProviderConnection(
        id="demo",
        label="gh:acme",
        provider_type="github",
        scope="org · 1 repos",
        auth_mode="GitHub App",
        granted_capabilities=set(),
    )


async def test_demo_interrogate_returns_repo(demo_connection) -> None:
    provider = DemoProvider("github")
    repo = await provider.interrogate(demo_connection, "widget")
    assert isinstance(repo, Repo)
    assert repo.id == "widget"
    assert repo.connection_id == demo_connection.id


async def test_demo_correct_config_pr_shape(demo_connection) -> None:
    provider = DemoProvider("github")
    repo = Repo(id="widget", connection_id=demo_connection.id)
    req = CorrectionRequest(repo=repo, check_id="license", check_label="LICENSE present",
                            kind=RemediationKind.config_pr)
    result = await provider.correct(demo_connection, req)
    assert isinstance(result, CorrectionResult)
    assert result.applied is True


async def test_demo_deep_link_correct_shape(demo_connection) -> None:
    provider = DemoProvider("github")
    repo = Repo(id="widget", connection_id=demo_connection.id)
    req = CorrectionRequest(repo=repo, check_id="two_fa", check_label="2FA",
                            kind=RemediationKind.deep_link)
    result = await provider.correct(demo_connection, req)
    assert result.applied is True
    assert result.deep_link_url is not None
    # deep_link() builds a URL into the provider host.
    link = provider.deep_link(demo_connection, repo, "two_fa")
    assert link.startswith("https://github.com/")
    assert "widget" in link
