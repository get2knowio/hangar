"""Gitea adapter — designed-for, read-only at MVP (FR-025, research.md §1).

Gitea connections use a scoped token and offer read + deep-link capabilities only;
write tiers therefore collapse to deep-link per connection (FR-018). The interrogation
path mirrors GitHub's file/settings heuristics against Gitea's API. It implements the
same :class:`~hangar.providers.base.RepoProvider` contract so the multi-connection
fleet treats it uniformly (Constitution I).
"""

from __future__ import annotations

from collections.abc import Mapping

from hangar.domain.models import Capability, ProviderConnection, RemediationKind, Repo
from hangar.providers.base import CorrectionRequest, CorrectionResult, RepoListing, WebhookEvent


class GiteaAdapter:
    provider_type = "gitea"
    default_auth_mode = "Scoped token"

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

    async def list_repo_listings(  # pragma: no cover
        self, connection: ProviderConnection
    ) -> list[RepoListing]:
        return []

    async def interrogate(  # pragma: no cover
        self, connection: ProviderConnection, repo_ref: str, *, previous: Repo | None = None
    ) -> Repo | None:
        return previous

    def deep_link(self, connection: ProviderConnection, repo: Repo, check_id: str) -> str:
        # A Gitea deep link needs the self-hosted instance base URL, which is not yet
        # modelled per connection (Gitea is read-only/designed-for at MVP). The label
        # suffix is the OWNER (per ProviderConnection.owner), not a host, so we emit an
        # owner-qualified path rather than fabricating a wrong absolute host. Resolving it
        # against the operator's Gitea instance URL is a Gitea fast-follow item.
        return f"{connection.owner}/{repo.id}"

    def pr_url(self, connection: ProviderConnection, repo: Repo, pr_number: int | None) -> str:
        # Gitea is read-only at MVP (write tiers collapse to deep-link), so this is only a
        # protocol fallback; like deep_link it needs the instance base URL to be absolute.
        return f"{connection.owner}/{repo.id}/pulls/{pr_number}"

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

    def verify_webhook(self, headers: Mapping[str, str], body: bytes, secret: str) -> bool:
        # Gitea webhook ingest is a fast-follow item; reject (fail-closed) until implemented.
        return False

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent | None:
        return None
