"""T058 — GiteaAdapter satisfies the RepoProvider contract; read + deep-link only."""

from __future__ import annotations

import inspect

from hangar.domain.models import Capability
from hangar.providers.base import RepoProvider
from hangar.providers.gitea.adapter import GiteaAdapter


def test_gitea_satisfies_protocol() -> None:
    adapter = GiteaAdapter()
    assert isinstance(adapter, RepoProvider)
    assert adapter.provider_type == "gitea"
    for name in ("interrogate", "list_repos", "correct", "subscribe"):
        assert inspect.iscoroutinefunction(getattr(adapter, name))
    assert not inspect.iscoroutinefunction(adapter.deep_link)


def test_gitea_declares_read_and_deep_link_only() -> None:
    caps = GiteaAdapter().declared_capabilities()
    assert isinstance(caps, set)
    assert Capability.deep_link in caps
    assert Capability.read_settings in caps
    assert Capability.read_files in caps
    assert Capability.read_alerts in caps
    # no write capabilities
    assert Capability.write_settings not in caps
    assert Capability.open_pull_request not in caps
