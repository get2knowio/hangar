"""Gitea adapter — read-only ``RepoProvider`` at this stage (Constitution I, FR-025).

A Gitea connection authenticates with a scoped personal access token and offers read +
deep-link capabilities; write tiers therefore collapse to deep-link per connection
(FR-018). Interrogation mirrors GitHub's file/settings heuristics against Gitea's
GitHub-shaped REST API (see ``detection.py``); all Gitea host/URL math lives in
``client.py``, so no platform string leaks into the core.
"""

from __future__ import annotations

from collections.abc import Mapping

from hangar.domain.models import Capability, ProviderConnection, RemediationKind, Repo
from hangar.providers.base import CorrectionRequest, CorrectionResult, RepoListing, WebhookEvent
from hangar.providers.gitea.client import _FORBIDDEN, GiteaClient, gitea_web_base


class GiteaAdapter:
    provider_type = "gitea"
    default_auth_mode = "Scoped token"

    def declared_capabilities(self) -> set[Capability]:
        # Read + deep-link only at this stage. ``read_alerts`` is intentionally absent:
        # OSS Gitea has no vulnerability-alert feed, so there is nothing to read and the
        # alert checks honestly resolve to ``unknown`` (Constitution VIII). Writes and
        # webhooks arrive in later stages.
        return {
            Capability.read_settings,
            Capability.read_files,
            Capability.deep_link,
        }

    def _client(self, connection: ProviderConnection) -> GiteaClient:
        from hangar.config import get_settings

        return GiteaClient(connection, timeout=get_settings().github_http_timeout_seconds)

    async def _list_repo_objects(self, connection: ProviderConnection) -> list[dict]:
        """Raw repo objects in scope (org listing, falling back to the user's)."""
        async with self._client(connection) as client:
            data = await client.get(
                f"/orgs/{connection.owner}/repos", {"limit": 50}
            )
            if not isinstance(data, list):
                data = await client.get(
                    f"/users/{connection.owner}/repos", {"limit": 50}
                )
        if data is _FORBIDDEN:
            raise RuntimeError(
                f"Gitea connection '{connection.id}' cannot list repos for owner "
                f"'{connection.owner}' (403 on both the org and user endpoints); "
                "check the token scope."
            )
        return data if isinstance(data, list) else []

    async def list_repos(self, connection: ProviderConnection) -> list[str]:
        return [r["name"] for r in await self._list_repo_objects(connection)]

    async def list_repo_listings(self, connection: ProviderConnection) -> list[RepoListing]:
        return [
            RepoListing(name=r["name"], private=bool(r.get("private")))
            for r in await self._list_repo_objects(connection)
        ]

    async def interrogate(
        self, connection: ProviderConnection, repo_ref: str, *, previous: Repo | None = None
    ) -> Repo | None:
        from hangar.providers.gitea.detection import interrogate_repo

        async with self._client(connection) as client:
            return await interrogate_repo(client, connection, repo_ref, previous)

    def deep_link(self, connection: ProviderConnection, repo: Repo, check_id: str) -> str:
        anchor = {
            "branch_protection": "/settings/branches",
            "conventional": "/settings/branches",
        }.get(check_id, "")
        return f"{gitea_web_base(connection.base_url)}/{connection.owner}/{repo.id}{anchor}"

    def pr_url(self, connection: ProviderConnection, repo: Repo, pr_number: int | None) -> str:
        web = gitea_web_base(connection.base_url)
        return f"{web}/{connection.owner}/{repo.id}/pulls/{pr_number}"

    async def correct(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:
        # Read-only connection: write tiers collapse to deep-link; report stays report
        # (FR-018). PR-first writes arrive in a later stage.
        if request.kind in (
            RemediationKind.deep_link,
            RemediationKind.settings_patch,
            RemediationKind.config_pr,
        ):
            return CorrectionResult(
                applied=True,
                deep_link_url=self.deep_link(connection, request.repo, request.check_id),
                summary="Opened in Gitea",
            )
        return CorrectionResult(applied=True, summary="Reported")

    async def subscribe(self, connection: ProviderConnection) -> None:
        return None

    def verify_webhook(self, headers: Mapping[str, str], body: bytes, secret: str) -> bool:
        # Gitea webhook ingest is a later stage; reject (fail-closed) until implemented.
        return False

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent | None:
        return None
