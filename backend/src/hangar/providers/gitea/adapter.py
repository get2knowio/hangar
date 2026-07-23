"""Gitea adapter — read + PR-first remediation ``RepoProvider`` (Constitution I, FR-025).

A Gitea connection authenticates with a scoped personal access token and offers read,
deep-link, and (when the operator declares the token writable) pull-request capabilities.
Interrogation mirrors GitHub's file/settings heuristics against Gitea's GitHub-shaped REST
API (see ``detection.py``); writes are **human-triggered and PR-first** — a remediation
file delivered on a fresh ``hangar/<check>`` branch via an opened pull request, never a
push/force-push (Constitution II, FR-014). All Gitea host/URL math lives in ``client.py``,
so no platform string leaks into the core. Webhook ingest arrives in a later stage.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping

from hangar.domain.models import Capability, ProviderConnection, RemediationKind, Repo
from hangar.providers.base import CorrectionRequest, CorrectionResult, RepoListing, WebhookEvent
from hangar.providers.bots import is_bot_login
from hangar.providers.gitea.client import _FORBIDDEN, GiteaClient, gitea_web_base

# Files/config Hangar writes via PR for the writable PR-tier checks. Mostly the same paths as
# GitHub, but Gitea is a Renovate (not Dependabot) world, so the update-bot remediation writes
# a ``renovate.json`` — and CODEOWNERS/templates use Gitea's ``.gitea/`` location. Each path is
# also a candidate in ``detection._FILE_CHECKS`` so the opened PR actually clears the finding.
_PR_FILES = {
    "license": "LICENSE",
    "security_md": "SECURITY.md",
    "codeowners": ".gitea/CODEOWNERS",
    "templates": ".gitea/ISSUE_TEMPLATE/bug_report.md",
    "dependabot_updates": "renovate.json",
    "cooldown": "renovate.json",
    "release_please": "release-please-config.json",
}


class GiteaAdapter:
    provider_type = "gitea"
    default_auth_mode = "Scoped token"

    def declared_capabilities(self) -> set[Capability]:
        # ``read_alerts`` is intentionally absent: OSS Gitea has no vulnerability-alert feed,
        # so the alert checks honestly resolve to ``unknown`` (Constitution VIII). ``open_pull
        # _request`` is offered (granted only on a writable connection) so PR-tier checks
        # remediate via a real PR; ``write_settings`` is not — none of the settings-patch
        # checks (e.g. Dependabot alerts) has a Gitea API, so those degrade to deep-link.
        return {
            Capability.read_settings,
            Capability.read_files,
            Capability.deep_link,
            Capability.open_pull_request,
            Capability.subscribe_webhooks,
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
            "signed_commits": "/settings/branches",
        }.get(check_id, "")
        return f"{gitea_web_base(connection.base_url)}/{connection.owner}/{repo.id}{anchor}"

    def pr_url(self, connection: ProviderConnection, repo: Repo, pr_number: int | None) -> str:
        web = gitea_web_base(connection.base_url)
        return f"{web}/{connection.owner}/{repo.id}/pulls/{pr_number}"

    async def correct(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:
        """Apply a human-triggered correction. PR-first; NEVER a push/force-push.

        The remediation service resolves the kind from the connection's granted tiers, so a
        read-only connection (no ``open_pull_request``) never reaches ``config_pr`` here — it
        sends ``deep_link`` instead (FR-018).
        """
        if request.kind is RemediationKind.deep_link:
            url = self.deep_link(connection, request.repo, request.check_id)
            return CorrectionResult(applied=True, deep_link_url=url, summary="Opened in Gitea")
        if request.kind is RemediationKind.report:
            return CorrectionResult(applied=True, summary="Reported")
        if request.kind is RemediationKind.config_pr:
            return await self._open_pr(connection, request)
        if request.kind is RemediationKind.settings_patch:
            # No Gitea settings-patch remediation exists (the patch-tier checks are GitHub-only),
            # and ``write_settings`` is never granted, so the service never sends this. Refuse
            # rather than fake a converged setting (fail-closed, Constitution VIII).
            raise ValueError(
                f"no settings-patch remediation for Gitea check '{request.check_id}'"
            )
        raise ValueError(f"unknown remediation kind: {request.kind}")

    async def _open_pr(
        self, connection: ProviderConnection, request: CorrectionRequest
    ) -> CorrectionResult:
        owner, repo = connection.owner, request.repo.id
        branch = f"hangar/{request.check_id}"
        base = request.repo.default_branch

        async with self._client(connection) as client:
            # Idempotency: surface an existing open Hangar PR for this (repo, check) rather
            # than opening a duplicate (FR-015). Gitea's pulls list carries each PR's head ref.
            existing = await client.get(
                f"/repos/{owner}/{repo}/pulls", {"state": "open", "limit": 50}
            )
            if isinstance(existing, list):
                for pr in existing:
                    if (pr.get("head") or {}).get("ref") == branch:
                        return CorrectionResult(
                            applied=True, pr_url=pr.get("html_url"), pr_number=pr.get("number"),
                            idempotent_hit=True, summary=f"PR #{pr.get('number')} already open",
                        )

            # Create a fresh branch off the default branch and commit the remediation file
            # onto it, then open a PR. The default branch is never written to directly.
            await client.post(
                f"/repos/{owner}/{repo}/branches",
                {"new_branch_name": branch, "old_branch_name": base},
            )
            path = _PR_FILES.get(request.check_id, f".gitea/hangar-{request.check_id}.md")
            content = base64.b64encode(
                f"# {request.check_label}\n\nAdded by Hangar to remediate "
                f"`{request.check_id}`.\n".encode()
            ).decode()
            await client.post(
                f"/repos/{owner}/{repo}/contents/{path}",
                {"content": content, "message": f"chore: {request.check_label} (via Hangar)",
                 "branch": branch},
            )
            pr = await client.post(
                f"/repos/{owner}/{repo}/pulls",
                {"title": f"{request.check_label} (via Hangar)", "head": branch, "base": base,
                 "body": "Opened by Hangar — review and merge to remediate this finding."},
            )
        return CorrectionResult(
            applied=True, pr_url=pr.get("html_url"), pr_number=pr.get("number"),
            summary=f"PR #{pr.get('number')} opened",
        )

    async def subscribe(self, connection: ProviderConnection) -> None:
        # Hangar verifies/parses inbound Gitea webhooks (below) but does not auto-register
        # them; the operator points the repo/org webhook at /api/v1/webhooks/<connection_id>
        # with the connection's secret. No-op, mirroring the GitHub adapter.
        return None

    # --------------------------------------------------------------- webhooks
    def verify_webhook(self, headers: Mapping[str, str], body: bytes, secret: str) -> bool:
        """Verify Gitea's ``X-Gitea-Signature`` HMAC (constant-time, fail-closed).

        Unlike GitHub's ``X-Hub-Signature-256: sha256=<hex>``, Gitea sends a **raw hex**
        HMAC-SHA256 digest with no algorithm prefix. A missing header or secret rejects.
        """
        h = {k.lower(): v for k, v in headers.items()}
        sig = h.get("x-gitea-signature")
        if not sig or not secret:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent | None:
        """Normalize a Gitea event (``X-Gitea-Event`` + payload) into a WebhookEvent."""
        h = {k.lower(): v for k, v in headers.items()}
        event = h.get("x-gitea-event", "")
        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            return None
        repo_name = (payload.get("repository") or {}).get("name")
        if not repo_name:
            return None
        if event == "status":
            # A commit-status event carries the combined state for the head commit.
            state = payload.get("state")
            if state == "success":
                return WebhookEvent(repo_name, ci_status="pass")
            if state in ("failure", "error"):
                return WebhookEvent(repo_name, ci_status="fail")
            return None
        if event == "pull_request":
            action = payload.get("action")
            if action in ("opened", "reopened", "closed"):
                delta = 1 if action in ("opened", "reopened") else -1
                login = ((payload.get("pull_request") or {}).get("user") or {}).get("login")
                return WebhookEvent(repo_name, pr_delta=delta, pr_is_bot=is_bot_login(login))
            return None
        return None
