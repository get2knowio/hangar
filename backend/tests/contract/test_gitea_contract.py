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


def test_gitea_declares_read_deep_link_and_pull_requests() -> None:
    caps = GiteaAdapter().declared_capabilities()
    assert isinstance(caps, set)
    assert Capability.deep_link in caps
    assert Capability.read_settings in caps
    assert Capability.read_files in caps
    # PR-first remediation is offered (granted only on a writable connection).
    assert Capability.open_pull_request in caps
    # read_alerts is intentionally NOT declared: OSS Gitea has no vulnerability-alert feed,
    # so the alert checks resolve to honest `unknown` rather than a fabricated state
    # (Constitution VIII).
    assert Capability.read_alerts not in caps
    # write_settings is NOT offered: no settings-patch check has a Gitea API, so those
    # degrade to deep-link rather than a fabricated converged setting.
    assert Capability.write_settings not in caps
