"""Provider adapter registry — maps a ``provider_type`` to its adapter (Constitution I).

Adding a provider is a registration here plus an adapter module; the core never learns
a new branch.
"""

from __future__ import annotations

from hangar.domain.models import ProviderConnection
from hangar.providers.base import RepoProvider
from hangar.providers.demo import DemoProvider
from hangar.providers.gitea.adapter import GiteaAdapter
from hangar.providers.github.adapter import GitHubAdapter

_ADAPTERS: dict[str, RepoProvider] = {
    "github": GitHubAdapter(),
    "gitea": GiteaAdapter(),
}


def get_provider(provider_type: str) -> RepoProvider:
    try:
        return _ADAPTERS[provider_type]
    except KeyError as exc:
        raise ValueError(f"no adapter registered for provider type '{provider_type}'") from exc


def provider_for(connection: ProviderConnection) -> RepoProvider:
    """Pick the adapter for a connection.

    A connection without a stored credential (the seeded/demo fixtures) is served by the
    :class:`DemoProvider`, which simulates corrections with no network I/O. A connection
    with a real credential uses the concrete adapter (live platform calls).
    """
    if not connection.has_credential:
        return DemoProvider(connection.provider_type)
    return get_provider(connection.provider_type)


def supported_types() -> list[str]:
    return list(_ADAPTERS)
