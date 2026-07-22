"""Gitea detection heuristics — real, read-only interrogation against Gitea's REST API.

Gitea's API is deliberately GitHub-shaped, so each catalog check maps to the same kind of
read (repo metadata, contents API, branch protection, pulls, releases) the GitHub adapter
uses — just under ``/api/v1`` and without conditional/ETag support (Gitea reads are fetched
fresh each poll). The signals GitHub exposes that OSS Gitea has no equivalent for —
Dependabot/vulnerability alerts, secret scanning, CodeQL code scanning, the Actions
``GITHUB_TOKEN`` permissions model, and an org-wide 2FA-required flag — are reported as
honest ``unknown`` (capability-gated), never a fabricated pass/fail (Constitution VIII).
"""

from __future__ import annotations

import asyncio

from hangar.domain.models import (
    AlertCounts,
    Capability,
    CIStatus,
    ProviderConnection,
    PullRequestSummary,
    Repo,
)
from hangar.domain.repo_config import HangarRepoConfig
from hangar.providers.bots import is_bot_login, pr_kind
from hangar.providers.gitea.client import _FORBIDDEN, _NOT_FOUND, GiteaClient

# Platform-neutral detection primitives, single-sourced from the GitHub reference adapter
# (workflow-ref parsing, SHA-pin logic, conventional-commit markers, update-bot config
# paths, the release-staleness threshold, and ISO-date parsing all apply unchanged here).
from hangar.providers.github.detection import (
    _CONVENTIONAL_ACTIONS,
    _CONVENTIONAL_CONFIGS,
    _DEPENDABOT_CONFIG_FILES,
    _PR_DETAIL_CAP,
    _RELEASE_STALE_DAYS,
    _RENOVATE_CONFIG_FILES,
    _USES_RE,
    _has_unpinned_action,
    _parse_dt,
)

# Signals GitHub exposes but OSS Gitea has no API for. Always reported as ``unknown`` —
# Hangar cannot determine them on Gitea, so it must not guess (Constitution VIII).
_GITHUB_ONLY_UNKNOWN = (
    "dependabot_alerts",     # no Dependabot / vulnerability-alerts service
    "secret_scanning",       # GitHub Advanced Security only
    "code_scanning",         # CodeQL / code-scanning analyses only
    "workflow_permissions",  # no GITHUB_TOKEN least-privilege model
    "two_fa",                # no org-wide 2FA-required enforcement flag
)

# Candidate paths whose presence satisfies a file-based check. Unlike GitHub (whose own
# license detection drives the ``license`` check from repo metadata), Gitea has no reliable
# SPDX field, so ``license`` is a file-presence check here — honest, if without an SPDX id.
_FILE_CHECKS = {
    "readme": ["README.md", "README.rst", "README"],
    "license": ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"],
    "security_md": ["SECURITY.md", ".github/SECURITY.md"],
    "codeowners": ["CODEOWNERS", ".gitea/CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"],
    "changelog": ["CHANGELOG.md", "CHANGELOG"],
    "lockfile": ["poetry.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                 "bun.lock", "bun.lockb", "uv.lock", "Cargo.lock"],
    "release_please": ["release-please-config.json", ".release-please-manifest.json"],
    "templates": [".gitea/ISSUE_TEMPLATE/config.yml", ".gitea/ISSUE_TEMPLATE",
                  ".gitea/PULL_REQUEST_TEMPLATE.md", ".github/ISSUE_TEMPLATE",
                  ".github/PULL_REQUEST_TEMPLATE.md"],
    "dependabot_updates": _DEPENDABOT_CONFIG_FILES + _RENOVATE_CONFIG_FILES,
}

# Gitea Actions reads workflows from .gitea/workflows; many repos mirror GitHub's location.
_WORKFLOW_DIRS = (".gitea/workflows", ".github/workflows")


async def interrogate_repo(
    client: GiteaClient,
    connection: ProviderConnection,
    repo_ref: str,
    previous: Repo | None = None,
) -> Repo | None:
    """Interrogate one Gitea repo into a normalized snapshot.

    Returns ``None`` when the repo is unreadable (404/403) so the caller keeps any cached
    snapshot rather than overwriting it with an empty one (Constitution VI).
    """
    owner = connection.owner
    granted = connection.granted_capabilities

    repo_data = await client.get(f"/repos/{owner}/{repo_ref}")
    if not isinstance(repo_data, dict):
        return None  # 404/403 → repo unreadable on this connection

    default_branch = repo_data.get("default_branch") or "main"
    description = repo_data.get("description") or ""

    fails: list[str] = []
    unknowns: list[str] = list(_GITHUB_ONLY_UNKNOWN)
    if default_branch != "main":
        fails.append("default_branch")

    (dyn_fails, dyn_unknowns, open_prs, bot_prs, ci, release_pending, pulls, has_topics) = (
        await _dynamic_checks(client, owner, repo_ref, default_branch, granted)
    )
    # "Description & topics set" — both are required (matches the catalog evidence string).
    if not (description and has_topics):
        fails.append("description")

    # The repo's committed .hangar.json opt-outs. Gated on file reads; unreadable → {}.
    suppressions: dict[str, str] = {}
    if Capability.read_files in granted:
        suppressions = await _read_suppressions(client, owner, repo_ref)

    fails += dyn_fails
    unknowns += dyn_unknowns
    return Repo(
        id=repo_ref,
        connection_id=connection.id,
        description=description,
        default_branch=default_branch,
        open_prs=open_prs,
        bot_prs=bot_prs,
        ci_status=ci,
        alerts=AlertCounts(),  # OSS Gitea has no vulnerability-alert feed
        release_pending_days=release_pending,
        fails=sorted(set(fails)),
        unknowns=sorted(set(unknowns) - set(fails)),
        suppressions=suppressions,
        license_spdx=None,  # Gitea exposes no reliable SPDX id
        pull_requests=[PullRequestSummary(**d) for d in pulls],
    )


async def _dynamic_checks(
    client: GiteaClient,
    owner: str,
    repo_ref: str,
    default_branch: str,
    granted: set[Capability],
) -> tuple[list[str], list[str], int, int, CIStatus, int | None, list[dict], bool]:
    """Every check that is read fresh each poll. A 403 on any resource yields ``unknown``
    for the affected check(s) rather than aborting the snapshot (Constitution VI/VIII)."""
    fails: list[str] = []
    unknowns: list[str] = []

    can_files = Capability.read_files in granted
    can_settings = Capability.read_settings in granted

    open_prs = bot_prs = 0
    pull_details: list[dict] = []
    ci = CIStatus.none
    release_pending: int | None = None
    has_topics = False

    async def _present(path: str) -> bool:
        r = await client.get(f"/repos/{owner}/{repo_ref}/contents/{path}")
        return r is not _NOT_FOUND and r is not _FORBIDDEN

    async def _files_group() -> None:
        if not can_files:
            unknowns.extend(_FILE_CHECKS)
            unknowns.append("cooldown")
            return

        async def _one(check_id: str, candidates: list[str]) -> tuple[str, str]:
            for path in candidates:
                r = await client.get(f"/repos/{owner}/{repo_ref}/contents/{path}")
                if r is _FORBIDDEN:
                    return check_id, "unknown"
                if r is not _NOT_FOUND:
                    return check_id, "present"
            return check_id, "absent"

        statuses = dict(await asyncio.gather(*(_one(c, p) for c, p in _FILE_CHECKS.items())))
        for cid, st in statuses.items():
            if st == "unknown":
                unknowns.append(cid)
            elif st == "absent":
                fails.append(cid)

        # cooldown is keyed off the update-bot config so a repo with no bot fails once.
        if statuses.get("dependabot_updates") == "unknown":
            unknowns.append("cooldown")
        elif statuses.get("dependabot_updates") == "absent":
            fails.append("cooldown")
        elif not await _has_cooldown(client, owner, repo_ref):
            fails.append("cooldown")

    async def _branch_protection_group() -> None:
        if not can_settings:
            unknowns.append("branch_protection")
            return
        prot = await client.get(
            f"/repos/{owner}/{repo_ref}/branch_protections/{default_branch}"
        )
        if prot is _FORBIDDEN:
            unknowns.append("branch_protection")
        elif prot is _NOT_FOUND:
            fails.append("branch_protection")

    async def _topics_group() -> None:
        nonlocal has_topics
        data = await client.get(f"/repos/{owner}/{repo_ref}/topics")
        if isinstance(data, dict):
            has_topics = bool(data.get("topics"))

    async def _workflows_group() -> None:
        if not can_files:
            unknowns.extend(["dep_review", "conventional", "actions_pinned_sha"])
            return
        refs = await _workflow_action_refs(client, owner, repo_ref)
        if not any("dependency-review-action" in r for r in refs):
            fails.append("dep_review")
        has_conv = any(any(a in r for a in _CONVENTIONAL_ACTIONS) for r in refs)
        if not has_conv:
            for p in _CONVENTIONAL_CONFIGS:
                if await _present(p):
                    has_conv = True
                    break
        if not has_conv:
            fails.append("conventional")
        if _has_unpinned_action(refs):
            fails.append("actions_pinned_sha")

    async def _release_group() -> None:
        nonlocal release_pending
        release_pending = await _release_pending_days(client, owner, repo_ref, default_branch)
        if release_pending is not None and release_pending >= _RELEASE_STALE_DAYS:
            fails.append("release_health")

    async def _pulls_group() -> None:
        nonlocal open_prs, bot_prs, pull_details
        open_prs, bot_prs, pull_details = await _pull_data(client, owner, repo_ref)

    async def _ci_group() -> None:
        nonlocal ci
        ci = await _ci_status(client, owner, repo_ref, default_branch)
        if ci is CIStatus.fail:
            fails.append("ci_workflow_green")
        elif ci is CIStatus.none:
            unknowns.append("ci_workflow_green")

    await asyncio.gather(
        _files_group(),
        _branch_protection_group(),
        _topics_group(),
        _workflows_group(),
        _release_group(),
        _pulls_group(),
        _ci_group(),
    )
    return fails, unknowns, open_prs, bot_prs, ci, release_pending, pull_details, has_topics


async def _read_text(client: GiteaClient, owner: str, repo: str, path: str) -> str | None:
    import base64

    data = await client.get(f"/repos/{owner}/{repo}/contents/{path}")
    if not isinstance(data, dict):
        return None
    if data.get("encoding") == "base64" and data.get("content"):
        try:
            return base64.b64decode(data["content"]).decode("utf-8", "replace")
        except ValueError:
            return None
    return None


async def _read_suppressions(client: GiteaClient, owner: str, repo: str) -> dict[str, str]:
    """Read + parse the repo's ``.hangar.json`` into a {check_id: reason} suppression map.

    Fail-safe: an absent file, a 403, or malformed content all yield ``{}`` — never an
    exception. Parsing is contained in ``HangarRepoConfig.parse`` (drops unknown ids).
    """
    raw = await _read_text(client, owner, repo, ".hangar.json")
    if raw is None:
        return {}
    config = HangarRepoConfig.parse(raw)
    return config.suppressions() if config else {}


async def _has_cooldown(client: GiteaClient, owner: str, repo: str) -> bool:
    """Whether the present update-bot config declares a cooldown (Dependabot ``cooldown:`` or
    Renovate ``minimumReleaseAge``/``stabilityDays``) — a lightweight substring check."""
    for path in _DEPENDABOT_CONFIG_FILES:
        content = await _read_text(client, owner, repo, path)
        if content is not None:
            return "cooldown" in content
    for path in _RENOVATE_CONFIG_FILES:
        content = await _read_text(client, owner, repo, path)
        if content is not None:
            return "minimumReleaseAge" in content or "stabilityDays" in content
    return False


async def _workflow_action_refs(client: GiteaClient, owner: str, repo: str) -> list[str]:
    """All ``uses:`` action references across the workflow directories (.gitea + .github)."""
    refs: list[str] = []
    for wf_dir in _WORKFLOW_DIRS:
        listing = await client.get(f"/repos/{owner}/{repo}/contents/{wf_dir}")
        if not isinstance(listing, list):
            continue
        for item in listing:
            name = item.get("name", "")
            if item.get("type") != "file" or not name.endswith((".yml", ".yaml")):
                continue
            text = await _read_text(client, owner, repo, item["path"])
            if not text:
                continue
            for line in text.splitlines():
                stripped = line.split("#", 1)[0]
                m = _USES_RE.match(stripped)
                if m:
                    refs.append(m.group(1))
    return refs


async def _release_pending_days(
    client: GiteaClient, owner: str, repo: str, branch: str
) -> int | None:
    """Days of unreleased commits = default-branch HEAD date − latest release date.

    None when there is no release or HEAD is not ahead of it. Gitea's branch resource
    carries the HEAD commit timestamp directly, so no separate commit lookup is needed.
    """
    rel = await client.get(f"/repos/{owner}/{repo}/releases/latest")
    if not isinstance(rel, dict):
        return None
    rel_dt = _parse_dt(rel.get("published_at"))
    if rel_dt is None:
        return None
    branch_data = await client.get(f"/repos/{owner}/{repo}/branches/{branch}")
    if not isinstance(branch_data, dict):
        return None
    head_dt = _parse_dt((branch_data.get("commit") or {}).get("timestamp"))
    if head_dt is None or head_dt <= rel_dt:
        return None
    return (head_dt - rel_dt).days


_MAX_PAGES = 10
_PULL_PAGE_SIZE = 50


async def _pull_data(client: GiteaClient, owner: str, repo: str) -> tuple[int, int, list[dict]]:
    """Open-PR count, dependency-bot count, and recent PR details (Gitea page/limit paging)."""
    data: list[dict] = []
    for page in range(1, _MAX_PAGES + 1):
        chunk = await client.get(
            f"/repos/{owner}/{repo}/pulls",
            {"state": "open", "sort": "recentupdate", "limit": _PULL_PAGE_SIZE, "page": page},
        )
        if not isinstance(chunk, list) or not chunk:
            break
        data.extend(chunk)
        if len(chunk) < _PULL_PAGE_SIZE:
            break

    bot = sum(1 for pr in data if is_bot_login((pr.get("user") or {}).get("login")))
    details: list[dict] = []
    for pr in data[:_PR_DETAIL_CAP]:
        login = (pr.get("user") or {}).get("login")
        details.append({
            "title": pr.get("title") or "",
            "number": pr.get("number"),
            "url": pr.get("html_url"),
            "kind": pr_kind(login),
            "created_at": pr.get("created_at"),
            "draft": bool(pr.get("draft")),
        })
    return len(data), bot, details


async def _ci_status(
    client: GiteaClient, owner: str, repo: str, branch: str
) -> CIStatus:
    """Default-branch CI from Gitea's combined commit status (``state`` field)."""
    data = await client.get(f"/repos/{owner}/{repo}/commits/{branch}/status")
    if not isinstance(data, dict):
        return CIStatus.none
    state = data.get("state")
    if state == "success":
        return CIStatus.passing
    if state in ("failure", "error"):
        return CIStatus.fail
    return CIStatus.none
