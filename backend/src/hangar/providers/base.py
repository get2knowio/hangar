"""The ``RepoProvider`` interface — the only seam between the provider-neutral core
and a platform (Constitution I).

Every adapter implements three verbs:

* ``interrogate`` — read a repo into a normalized :class:`~hangar.domain.models.Repo`
  snapshot (read-only; never mutates).
* ``correct`` — apply a human-triggered remediation (settings PATCH or a PR — never
  a push/force-push, Constitution II).
* ``subscribe`` — register for provider events (webhooks) where supported.

An adapter also declares the :class:`~hangar.domain.models.Capability` set it can
offer; a *connection* holds the subset its granted scopes actually permit. Checks
reference capabilities, never platform branches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from hangar.domain.models import (
    Capability,
    ProviderConnection,
    RemediationKind,
    Repo,
)

# Canonical provider-type → display name (single source of truth).
PROVIDER_NAMES = {"github": "GitHub", "gitea": "Gitea"}


def provider_name(provider_type: str) -> str:
    return PROVIDER_NAMES.get(provider_type, provider_type.title())


@dataclass(slots=True)
class CorrectionResult:
    """Outcome of a ``correct`` call."""

    applied: bool
    pr_url: str | None = None
    pr_number: int | None = None
    deep_link_url: str | None = None
    idempotent_hit: bool = False
    summary: str = ""


@dataclass(slots=True)
class CorrectionRequest:
    repo: Repo
    check_id: str
    check_label: str
    kind: RemediationKind


@runtime_checkable
class RepoProvider(Protocol):
    """Provider adapter contract. Implemented by GitHub (MVP) and Gitea (deferred)."""

    provider_type: str

    def declared_capabilities(self) -> set[Capability]:
        """The full capability set this adapter *can* offer."""
        ...

    async def interrogate(
        self, connection: ProviderConnection, repo_ref: str, *, previous: Repo | None = None
    ) -> Repo | None:
        """Read a repository into a normalized snapshot (read-only).

        ``previous`` is the last cached snapshot, if any. Returns None when the repo is
        unreadable or unchanged with nothing to carry forward, so the caller keeps the
        cached snapshot.
        """
        ...

    async def list_repos(self, connection: ProviderConnection) -> list[str]:
        """List repository refs in the connection's scope (auto-discovery, FR-034)."""
        ...

    async def correct(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:
        """Apply a human-triggered correction. PR-first, idempotent (Constitution II)."""
        ...

    def deep_link(self, connection: ProviderConnection, repo: Repo, check_id: str) -> str:
        """Build a deep link into the provider UI for a finding."""
        ...

    def pr_url(self, connection: ProviderConnection, repo: Repo, pr_number: int | None) -> str:
        """Build the URL for a Hangar-opened pull request (provider-specific)."""
        ...

    async def subscribe(self, connection: ProviderConnection) -> None:
        """Register for provider events where supported (no-op otherwise)."""
        ...
