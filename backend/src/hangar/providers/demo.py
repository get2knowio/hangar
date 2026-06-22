"""Demo provider — simulates corrections for credential-less (seeded) connections.

The prototype fixtures have no real credentials, and Hangar must be demoable and its
tests deterministic without a live platform. For any connection without a stored
credential, corrections are *simulated* exactly as the prototype's ``fire``/``deep``
do — opening a (synthetic) PR or applying settings, with no network I/O — while a
connection with a real credential is served by the concrete adapter. The remediation
service owns idempotency/audit/state, so the simulation only needs to return the shape.
"""

from __future__ import annotations

from hangar.domain.models import Capability, ProviderConnection, RemediationKind, Repo
from hangar.providers.base import CorrectionRequest, CorrectionResult, provider_name

_PROVIDER_HOST = {"github": "github.com", "gitea": "gitea.local"}


class DemoProvider:
    def __init__(self, provider_type: str) -> None:
        self.provider_type = provider_type

    def declared_capabilities(self) -> set[Capability]:
        return set()

    async def list_repos(self, connection: ProviderConnection) -> list[str]:
        # No discovery for demo connections — seeded snapshots stand as-is.
        return []

    async def interrogate(
        self, connection: ProviderConnection, repo_ref: str, *, previous: Repo | None = None
    ) -> Repo | None:
        # Demo connections have no live data; the seeded snapshot stands as-is. Prefer the
        # cached snapshot so a refresh never clobbers rich fixtures with empty defaults.
        return previous if previous is not None else Repo(id=repo_ref, connection_id=connection.id)

    def deep_link(self, connection: ProviderConnection, repo: Repo, check_id: str) -> str:
        host = _PROVIDER_HOST.get(self.provider_type, "example.com")
        return f"https://{host}/{connection.owner}/{repo.id}"

    def pr_url(self, connection: ProviderConnection, repo: Repo, pr_number: int | None) -> str:
        host = _PROVIDER_HOST.get(self.provider_type, "example.com")
        return f"https://{host}/{connection.owner}/{repo.id}/pull/{pr_number}"

    async def correct(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:
        name = provider_name(self.provider_type)
        if request.kind is RemediationKind.deep_link:
            return CorrectionResult(
                applied=True,
                deep_link_url=self.deep_link(connection, request.repo, request.check_id),
                summary=f"Opened in {name}",
            )
        if request.kind is RemediationKind.report:
            return CorrectionResult(applied=True, summary="Reported")
        if request.kind is RemediationKind.settings_patch:
            return CorrectionResult(applied=True, summary="Settings applied")
        # config_pr — the service assigns the PR number and builds the URL.
        return CorrectionResult(applied=True, summary="PR opened")

    async def subscribe(self, connection: ProviderConnection) -> None:
        return None
