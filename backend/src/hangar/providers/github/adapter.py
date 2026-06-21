"""GitHub adapter — the MVP ``RepoProvider`` (Constitution I, research.md §1–2).

Auth is a **GitHub App** installation per connection: ``githubkit``'s
``AppInstallationAuthStrategy`` signs a short-lived JWT with the App private key and
exchanges it for an installation access token (minted, cached and refreshed by
githubkit), giving least-privilege per-connection scopes. A PAT/token connection uses
``TokenAuthStrategy``. There is no anonymous fallback — the adapter raises if no
credential is attached.

Reads are **real conditional requests**: each resource is fetched with
``If-None-Match`` from a per-connection ETag store; a ``304 Not Modified`` skips the
re-download and tells the poller the snapshot is unchanged (SC-010, Constitution VI).
Writes are **human-triggered, PR-first** — settings via a scoped PATCH, content via an
opened pull request, **never a push/force-push** (Constitution II, FR-014).
"""

from __future__ import annotations

import base64

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
    """Concrete adapter. Holds a per-connection ETag store across poll cycles."""

    provider_type = "github"
    base_url = "https://github.com"

    def __init__(self) -> None:
        # (connection_id, resource_path) -> ETag, persisted for the process lifetime so
        # the long-lived poller issues genuine conditional requests across cycles.
        self._etags: dict[tuple[str, str], str] = {}

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

    # ------------------------------------------------------------------ auth
    def _client(self, connection: ProviderConnection):
        """Build an authenticated githubkit client (real GitHub App or token auth).

        http_cache is disabled because we manage conditional requests explicitly.
        """
        from githubkit import (
            AppInstallationAuthStrategy,
            GitHub,
            TokenAuthStrategy,
        )

        if not connection.token:
            raise RuntimeError(
                f"GitHub connection '{connection.id}' has no decrypted credential attached; "
                "cannot authenticate (call attach_credential before using the adapter)."
            )
        if connection.app_id and connection.installation_id:
            auth = AppInstallationAuthStrategy(
                connection.app_id, connection.token, int(connection.installation_id)
            )
        else:
            auth = TokenAuthStrategy(connection.token)
        return GitHub(auth, http_cache=False)

    # --------------------------------------------------- conditional requests
    async def _conditional_get(
        self, gh, connection_id: str, path: str, params: dict | None = None, *, conditional: bool = False
    ):
        """GET ``path``. Returns the JSON body, ``NOT_FOUND`` (404), or — only when
        ``conditional=True`` — ``NOT_MODIFIED`` (304).

        Conditional (``If-None-Match``) requests are used ONLY for the primary repo
        resource: its ETag changes on any push/metadata edit, so a 304 means the repo is
        genuinely unchanged and the whole poll can be skipped (SC-010). Sub-resources are
        fetched unconditionally so their value is always fresh (recomputed each poll).
        """
        from githubkit.exception import RequestFailed

        key = (connection_id, path)
        headers = {}
        if conditional and (etag := self._etags.get(key)) is not None:
            headers["If-None-Match"] = etag
        try:
            resp = await gh.arequest("GET", path, params=params, headers=headers)
        except RequestFailed as exc:
            # 404 = resource absent (e.g. a file/ruleset that doesn't exist). Any other
            # error (403/5xx) propagates to the poller's resilience boundary.
            if exc.response.status_code == 404:
                return _NOT_FOUND
            raise
        if resp.status_code == 304:  # githubkit passes 304 through (not an error)
            return _NOT_MODIFIED
        if conditional and (new_etag := resp.headers.get("ETag")) is not None:
            self._etags[key] = new_etag
        return resp.json()

    async def list_repos(self, connection: ProviderConnection) -> list[str]:
        gh = self._client(connection)
        data = await self._conditional_get(
            gh, connection.id, f"/orgs/{connection.owner}/repos", params={"per_page": 100}
        )
        if data in (_NOT_MODIFIED, _NOT_FOUND):
            # Fall back to user repos if the owner isn't an org.
            data = await self._conditional_get(
                gh, connection.id, f"/users/{connection.owner}/repos", params={"per_page": 100}
            )
        if not isinstance(data, list):
            return []
        return [r["name"] for r in data]

    async def interrogate(self, connection: ProviderConnection, repo_ref: str) -> Repo | None:
        """Read a repo into a normalized snapshot, or None if unchanged since last poll."""
        from hangar.providers.github.detection import interrogate_repo

        return await interrogate_repo(self, self._client(connection), connection, repo_ref)

    # ----------------------------------------------------------------- writes
    def deep_link(self, connection: ProviderConnection, repo: Repo, check_id: str) -> str:
        anchor = {
            "two_fa": "/settings/security",
            "branch_protection": "/settings/branches",
            "secret_scanning": "/settings/security_analysis",
            "code_scanning": "/security/code-scanning",
            "dep_review": "/settings/security_analysis",
            "conventional": "/settings/rules",
            "workflow_permissions": "/settings/actions",
            "actions_pinned_sha": "/settings/actions",
        }.get(check_id, "")
        return f"{self.base_url}/{connection.owner}/{repo.id}{anchor}"

    async def correct(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:
        """Apply a human-triggered correction. PR-first; settings via scoped PATCH.

        NEVER pushes to or force-pushes a branch: content changes are delivered
        exclusively as an opened pull request (Constitution II, FR-014).
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
    ) -> CorrectionResult:
        gh = self._client(connection)
        owner, repo = connection.owner, request.repo.id
        if request.check_id == "dependabot_alerts":
            await gh.rest.repos.async_enable_vulnerability_alerts(owner=owner, repo=repo)
        elif request.check_id == "description":
            await gh.rest.repos.async_update(owner=owner, repo=repo, description=request.repo.description)
        return CorrectionResult(applied=True, summary="Settings applied")

    async def _open_pr(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:
        gh = self._client(connection)
        owner, repo = connection.owner, request.repo.id
        branch = f"hangar/{request.check_id}"
        head = request.repo.default_branch

        # Idempotency: surface an existing open Hangar PR for this (repo, check) (FR-015).
        existing = await gh.rest.pulls.async_list(
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
        ref = await gh.rest.git.async_get_ref(owner=owner, repo=repo, ref=f"heads/{head}")
        await gh.rest.git.async_create_ref(
            owner=owner, repo=repo, ref=f"refs/heads/{branch}", sha=ref.parsed_data.object_.sha
        )
        path = _PR_FILES.get(request.check_id, f".github/hangar-{request.check_id}.md")
        body = base64.b64encode(
            f"# {request.check_label}\n\nAdded by Hangar to remediate `{request.check_id}`.\n".encode()
        ).decode()
        await gh.rest.repos.async_create_or_update_file_contents(
            owner=owner, repo=repo, path=path,
            message=f"chore: {request.check_label} (via Hangar)", content=body, branch=branch,
        )
        pr = await gh.rest.pulls.async_create(
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


class _Sentinel:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{self.name}>"


_NOT_MODIFIED = _Sentinel("NOT_MODIFIED")
_NOT_FOUND = _Sentinel("NOT_FOUND")
