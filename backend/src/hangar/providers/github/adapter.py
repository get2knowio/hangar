"""GitHub adapter — the MVP ``RepoProvider`` (Constitution I, research.md §1–2).

Auth is a **GitHub App** installation per connection (least privilege, per-connection
scopes, webhooks). Reads use conditional requests (ETag) and a per-connection token
budget (Constitution VI). Writes are **human-triggered, PR-first** — settings via a
scoped PATCH, content via an opened pull request, **never a push/force-push**
(Constitution II).

``githubkit`` is imported lazily so this module loads in environments that run on the
seeded snapshot without the dependency; it is only required to talk to a live GitHub.
The detection heuristics (interrogation → pass/fail/unknown) live in
:mod:`hangar.providers.github.detection`.
"""

from __future__ import annotations

from hangar.domain.models import (
    Capability,
    ProviderConnection,
    RemediationKind,
    Repo,
)
from hangar.providers.base import CorrectionRequest, CorrectionResult

# Files/config Hangar writes via PR for the writable PR-tier checks (research.md §9).
_PR_FILES = {
    "license": "LICENSE",
    "security_md": "SECURITY.md",
    "codeowners": ".github/CODEOWNERS",
    "templates": ".github/ISSUE_TEMPLATE/bug_report.md",
    "dependabot_updates": ".github/dependabot.yml",
    "cooldown": ".github/dependabot.yml",
    "release_please": "release-please-config.json",
}


class GitHubAdapter:
    """Concrete adapter. Stateless except a per-instance ETag cache."""

    provider_type = "github"
    base_url = "https://github.com"

    def __init__(self) -> None:
        self._etags: dict[str, str] = {}

    def declared_capabilities(self) -> set[Capability]:
        return {
            Capability.read_settings,
            Capability.read_files,
            Capability.read_alerts,
            Capability.read_org_policy,
            Capability.write_settings,
            Capability.open_pull_request,
            Capability.deep_link,
            Capability.subscribe_webhooks,
        }

    # ------------------------------------------------------------------ reads
    def _client(self, connection: ProviderConnection):  # pragma: no cover - needs live creds
        from githubkit import GitHub  # lazy import

        # Real deployments mint an installation token from the stored App credential.
        # The credential is decrypted by the connection service and passed via env/secret;
        # here we accept a token on the connection's auth context if present.
        token = getattr(connection, "_token", None)
        return GitHub(token) if token else GitHub()

    async def list_repos(self, connection: ProviderConnection) -> list[str]:  # pragma: no cover
        client = self._client(connection)
        owner = connection.scope.split("·")[0].strip() or connection.label.split(":")[-1]
        resp = await client.rest.repos.async_list_for_org(org=owner, per_page=100)
        return [r.name for r in resp.parsed_data]

    async def interrogate(self, connection: ProviderConnection, repo_ref: str) -> Repo:  # pragma: no cover
        from hangar.providers.github.detection import interrogate_repo

        return await interrogate_repo(self._client(connection), connection, repo_ref, self._etags)

    # ----------------------------------------------------------------- writes
    def deep_link(self, connection: ProviderConnection, repo: Repo, check_id: str) -> str:
        owner = repo.connection_id  # display-only; real owner derived from connection scope
        settings_anchor = {
            "two_fa": "/settings/security",
            "branch_protection": "/settings/branches",
            "secret_scanning": "/settings/security_analysis",
            "code_scanning": "/security/code-scanning",
            "dep_review": "/settings/security_analysis",
            "conventional": "/settings/rules",
            "workflow_permissions": "/settings/actions",
            "actions_pinned_sha": "/settings/actions",
        }.get(check_id, "")
        return f"{self.base_url}/{owner}/{repo.id}{settings_anchor}"

    async def correct(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:
        """Apply a human-triggered correction. PR-first; settings via scoped PATCH.

        This method NEVER pushes to or force-pushes a branch: content changes are
        delivered exclusively as an opened pull request (Constitution II, FR-014).
        The live-GitHub I/O is exercised by integration tests with a mocked client;
        the orchestration/idempotency lives in :mod:`hangar.domain.remediation`.
        """
        if request.kind is RemediationKind.deep_link:
            url = self.deep_link(connection, request.repo, request.check_id)
            return CorrectionResult(applied=True, deep_link_url=url, summary="Opened in GitHub")
        if request.kind is RemediationKind.report:
            return CorrectionResult(applied=True, summary="Reported")
        if request.kind is RemediationKind.settings_patch:
            return await self._apply_settings(connection, request)
        if request.kind is RemediationKind.config_pr:
            return await self._open_pr(connection, request)
        raise ValueError(f"unknown remediation kind: {request.kind}")

    async def _apply_settings(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:  # pragma: no cover - needs live creds
        client = self._client(connection)
        owner = connection.label.split(":")[-1]
        repo = request.repo.id
        if request.check_id == "dependabot_alerts":
            await client.rest.repos.async_enable_vulnerability_alerts(owner=owner, repo=repo)
        elif request.check_id == "description":
            await client.rest.repos.async_update(
                owner=owner, repo=repo, description=f"{request.repo.description}"
            )
        return CorrectionResult(applied=True, summary="Settings applied")

    async def _open_pr(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:  # pragma: no cover - needs live creds
        client = self._client(connection)
        owner = connection.label.split(":")[-1]
        repo = request.repo.id
        branch = f"hangar/{request.check_id}"
        head = request.repo.default_branch

        # Idempotency: surface an existing open Hangar PR for this (repo, check) (FR-015).
        existing = await client.rest.pulls.async_list(
            owner=owner, repo=repo, state="open", head=f"{owner}:{branch}"
        )
        if existing.parsed_data:
            pr = existing.parsed_data[0]
            return CorrectionResult(
                applied=True, pr_url=pr.html_url, pr_number=pr.number, idempotent_hit=True,
                summary=f"PR #{pr.number} already open",
            )

        # Create a branch off the default branch and commit the remediation file, then
        # open a PR. No direct push to the default branch ever occurs.
        ref = await client.rest.git.async_get_ref(owner=owner, repo=repo, ref=f"heads/{head}")
        await client.rest.git.async_create_ref(
            owner=owner, repo=repo, ref=f"refs/heads/{branch}", sha=ref.parsed_data.object_.sha
        )
        path = _PR_FILES.get(request.check_id, f".github/hangar-{request.check_id}.md")
        content = _remediation_body(request.check_id, request.check_label)
        await client.rest.repos.async_create_or_update_file_contents(
            owner=owner, repo=repo, path=path,
            message=f"chore: {request.check_label} (via Hangar)",
            content=content, branch=branch,
        )
        pr = await client.rest.pulls.async_create(
            owner=owner, repo=repo, title=f"{request.check_label} (via Hangar)",
            head=branch, base=head,
            body="Opened by Hangar — review and merge to remediate this finding.",
        )
        return CorrectionResult(
            applied=True, pr_url=pr.parsed_data.html_url, pr_number=pr.parsed_data.number,
            summary=f"PR #{pr.parsed_data.number} opened",
        )

    async def subscribe(self, connection: ProviderConnection) -> None:
        return None


def _remediation_body(check_id: str, label: str) -> str:  # pragma: no cover
    import base64

    text = f"# {label}\n\nAdded by Hangar to remediate the `{check_id}` finding.\n"
    return base64.b64encode(text.encode()).decode()
