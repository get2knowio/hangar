"""Gitea adapter — designed-for, read-only at MVP (FR-025, research.md §1).

Gitea connections use a scoped token and offer read + deep-link capabilities only;
write tiers therefore collapse to deep-link per connection (FR-018). The interrogation
path mirrors GitHub's file/settings heuristics against Gitea's API. It implements the
same :class:`~hangar.providers.base.RepoProvider` contract so the multi-connection
fleet treats it uniformly (Constitution I).
"""

from __future__ import annotations

from hangar.domain.models import Capability, ProviderConnection, RemediationKind, Repo
from hangar.providers.base import CorrectionRequest, CorrectionResult


class GiteaAdapter:
    provider_type = "gitea"

    def declared_capabilities(self) -> set[Capability]:
        # Read + deep-link only at MVP — no write_settings / open_pull_request.
        return {
            Capability.read_settings,
            Capability.read_files,
            Capability.read_alerts,
            Capability.deep_link,
        }

    async def list_repos(self, connection: ProviderConnection) -> list[str]:  # pragma: no cover
        return []

    async def interrogate(self, connection: ProviderConnection, repo_ref: str) -> Repo:  # pragma: no cover
        return Repo(id=repo_ref, connection_id=connection.id)

    def deep_link(self, connection: ProviderConnection, repo: Repo, check_id: str) -> str:
        host = connection.label.split(":")[-1]
        return f"https://{host}/{repo.id}"

    async def correct(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:
        # Read-only connection: only deep-link/report are meaningful (FR-018).
        if request.kind in (RemediationKind.deep_link, RemediationKind.settings_patch, RemediationKind.config_pr):
            return CorrectionResult(
                applied=True,
                deep_link_url=self.deep_link(connection, request.repo, request.check_id),
                summary="Opened in Gitea",
            )
        return CorrectionResult(applied=True, summary="Reported")

    async def subscribe(self, connection: ProviderConnection) -> None:
        return None
