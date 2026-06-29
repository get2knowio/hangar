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
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import TYPE_CHECKING

from hangar.domain.models import (
    Capability,
    ProviderConnection,
    RemediationKind,
    Repo,
)
from hangar.providers.base import CorrectionRequest, CorrectionResult, RepoListing, WebhookEvent

if TYPE_CHECKING:
    from githubkit import (
        AppInstallationAuthStrategy,
        GitHub,
        TokenAuthStrategy,
    )
    from githubkit.retry import RetryChainDecision

# Retry policy for the githubkit client: back off and retry on a rate-limit / secondary
# (concurrency) limit — honoring the server's Retry-After — and on a transient 5xx, before
# giving up. A little more patient than githubkit's default (rate-limit retried once) because
# a single homelab token shares GitHub's secondary-limit budget across the whole fleet. When
# retries are exhausted the call raises and the caller degrades that repo/connection to its
# last good snapshot (sync.py), so this never blocks the poll cycle indefinitely.
_RETRY: RetryChainDecision | None = None


def _retry_policy() -> RetryChainDecision:
    """Lazily build (and cache) the retry chain so importing the adapter doesn't import
    githubkit at module load — its imports are deferred everywhere else here too."""
    global _RETRY
    if _RETRY is None:
        from githubkit.retry import RetryChainDecision, RetryRateLimit, RetryServerError

        _RETRY = RetryChainDecision(RetryRateLimit(max_retry=3), RetryServerError(max_retry=2))
    return _RETRY


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
    # Default human label for a GitHub connection's auth mode (provider-owned so the
    # provider-neutral connections service never branches on the platform name).
    default_auth_mode = "GitHub App"

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
    def _client(self, connection: ProviderConnection) -> GitHub:
        """Build an authenticated githubkit client (real GitHub App or token auth).

        Resilience (Constitution VI): a bounded per-request ``timeout`` so a hung GitHub
        connection can't stall the whole poll cycle; a ``LocalThrottler`` caps the burst of
        concurrent sub-requests one repo's interrogation fans out (avoids GitHub's secondary
        concurrency rate limit); and ``auto_retry`` backs off on a primary/secondary
        rate-limit (honoring ``Retry-After``) or a transient 5xx before giving up — a single
        exhausted repo then degrades to its last snapshot, never the whole cycle.

        http_cache is disabled because we manage conditional requests explicitly.
        """
        from githubkit import (
            AppInstallationAuthStrategy,
            GitHub,
            TokenAuthStrategy,
        )
        from githubkit.throttling import LocalThrottler

        from hangar.config import get_settings

        if not connection.token:
            raise RuntimeError(
                f"GitHub connection '{connection.id}' has no decrypted credential attached; "
                "cannot authenticate (call attach_credential before using the adapter)."
            )
        auth: AppInstallationAuthStrategy | TokenAuthStrategy
        has_app_id = connection.app_id is not None
        has_installation = connection.installation_id is not None
        if connection.app_id is not None and connection.installation_id is not None:
            auth = AppInstallationAuthStrategy(
                connection.app_id, connection.token, int(connection.installation_id)
            )
        elif has_app_id or has_installation:
            # A half-configured App would otherwise fall through to TokenAuthStrategy and
            # send the App private-key PEM as a bearer token. Fail closed with a clear error.
            raise RuntimeError(
                f"GitHub connection '{connection.id}' is a partial GitHub App config: "
                "both app_id and installation_id are required (or set neither for a token/PAT)."
            )
        else:
            auth = TokenAuthStrategy(connection.token)
        settings = get_settings()
        return GitHub(
            auth,
            http_cache=False,
            timeout=settings.github_http_timeout_seconds,
            throttler=LocalThrottler(max_concurrency=settings.github_max_concurrency),
            auto_retry=_retry_policy(),
        )

    # --------------------------------------------------- conditional requests
    async def _conditional_get(
        self,
        gh: GitHub,
        connection_id: str,
        path: str,
        params: dict | None = None,
        *,
        conditional: bool = False,
    ) -> object:
        """GET ``path``. Returns the JSON body, ``NOT_FOUND`` (404), or — only when
        ``conditional=True`` — ``NOT_MODIFIED`` (304).

        Conditional (``If-None-Match``) requests are used ONLY for the primary repo
        resource: its ETag changes on any push/metadata edit, so a 304 lets the caller
        reuse the repo-body-derived checks from the prior snapshot (SC-010). Sub-resources
        are fetched unconditionally so their value is always fresh (recomputed each poll).

        Returns the JSON body, or a sentinel: ``NOT_FOUND`` (404), ``FORBIDDEN`` (403 —
        feature disabled / insufficient fine-grained scope; the caller maps it to
        ``unknown``), or — only when ``conditional=True`` — ``NOT_MODIFIED`` (304).
        """
        from githubkit.exception import RequestFailed

        key = (connection_id, path)
        headers = {}
        if conditional and (etag := self._etags.get(key)) is not None:
            headers["If-None-Match"] = etag
        try:
            resp = await gh.arequest("GET", path, params=params, headers=headers)
        except RequestFailed as exc:
            # 404 = resource absent (e.g. a file/ruleset that doesn't exist).
            # 403 = readable repo but this resource/feature is unavailable to the token
            #       (GitHub Advanced Security off, narrower fine-grained scope) → unknown,
            #       NOT an exception that would abort the whole snapshot. 5xx propagates.
            if exc.response.status_code == 404:
                return _NOT_FOUND
            if exc.response.status_code == 403:
                return _FORBIDDEN
            raise
        if resp.status_code == 304:  # githubkit passes 304 through (not an error)
            return _NOT_MODIFIED
        if resp.status_code == 204:  # No Content (e.g. vulnerability-alerts = enabled)
            return _NO_CONTENT
        if conditional and (new_etag := resp.headers.get("ETag")) is not None:
            self._etags[key] = new_etag
        return resp.json()

    async def _list_repo_objects(self, connection: ProviderConnection) -> list[dict]:
        """The raw repo objects in scope (org listing, falling back to the user's).

        Shared by ``list_repos`` (names for the poller) and ``list_repo_listings``
        (names + visibility for the picker) so both see the same discovery + 403 handling.
        """
        gh = self._client(connection)
        data = await self._conditional_get(
            gh, connection.id, f"/orgs/{connection.owner}/repos", params={"per_page": 100}
        )
        if not isinstance(data, list):
            # Not an org (404), the org listing is forbidden (403), or unchanged — fall
            # back to the user's repos (the owner may be a personal account, or the token
            # may only see user-scoped repos).
            data = await self._conditional_get(
                gh, connection.id, f"/users/{connection.owner}/repos", params={"per_page": 100}
            )
        if data is _FORBIDDEN:
            # Forbidden on BOTH endpoints: the repo list is undeterminable, not empty.
            # Raise so the poller degrades to "serve last good snapshots" (SC-009) instead
            # of silently reporting zero repos that looks like an empty org.
            raise RuntimeError(
                f"GitHub connection '{connection.id}' cannot list repos for owner "
                f"'{connection.owner}' (403 on both the org and user endpoints); "
                "check the token/installation scope."
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
        """Read a repo into a normalized snapshot.

        ``previous`` is the last cached snapshot (if any); on a primary-resource 304 its
        repo-body-derived checks are carried forward while volatile signals re-evaluate.
        """
        from hangar.providers.github.detection import interrogate_repo

        return await interrogate_repo(
            self, self._client(connection), connection, repo_ref, previous
        )

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

    def pr_url(self, connection: ProviderConnection, repo: Repo, pr_number: int | None) -> str:
        return f"{self.base_url}/{connection.owner}/{repo.id}/pull/{pr_number}"

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
            return CorrectionResult(applied=True, summary="Dependabot alerts enabled")
        # A settings PATCH must converge the finding. Anything not handled here would be a
        # silent no-op that falsely reports success, so refuse it (checks that Hangar
        # cannot auto-apply are modelled as link/report tiers, not settings_patch).
        raise ValueError(
            f"no settings-patch remediation implemented for check '{request.check_id}'"
        )

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
            # githubkit types parsed_data as Optional and mypy doesn't narrow the
            # property access on re-read; the truthiness guard above ensures it is a
            # non-empty list here.
            pr = existing.parsed_data[0]  # type: ignore[index]
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

    # --------------------------------------------------------------- webhooks
    def verify_webhook(self, headers: Mapping[str, str], body: bytes, secret: str) -> bool:
        """Verify a GitHub ``X-Hub-Signature-256`` HMAC (constant-time)."""
        h = {k.lower(): v for k, v in headers.items()}
        sig = h.get("x-hub-signature-256")
        if not sig or not sig.startswith("sha256="):
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig.split("=", 1)[1])

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent | None:
        """Normalize a GitHub event (X-GitHub-Event + payload) into a WebhookEvent."""
        h = {k.lower(): v for k, v in headers.items()}
        event = h.get("x-github-event", "")
        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            return None
        repo_name = (payload.get("repository") or {}).get("name")
        if not repo_name:
            return None
        if event in ("check_suite", "workflow_run"):
            conclusion = (payload.get(event) or {}).get("conclusion")
            if conclusion == "success":
                return WebhookEvent(repo_name, ci_status="pass")
            if conclusion == "failure":
                return WebhookEvent(repo_name, ci_status="fail")
            return None
        if event == "pull_request":
            action = payload.get("action")
            if action in ("opened", "reopened", "closed"):
                delta = 1 if action in ("opened", "reopened") else -1
                login = ((payload.get("pull_request") or {}).get("user") or {}).get("login")
                is_bot = login in ("dependabot[bot]", "dependabot-preview[bot]")
                return WebhookEvent(repo_name, pr_delta=delta, pr_is_bot=is_bot)
            return None
        # vulnerability/dependabot alert events: reconcile on the next poll (nothing to apply).
        return None


class _Sentinel:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{self.name}>"


_NOT_MODIFIED = _Sentinel("NOT_MODIFIED")
_NOT_FOUND = _Sentinel("NOT_FOUND")
_FORBIDDEN = _Sentinel("FORBIDDEN")
_NO_CONTENT = _Sentinel("NO_CONTENT")
