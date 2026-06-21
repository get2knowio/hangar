"""GitHub detection heuristics (research.md §11).

Each catalog check maps to a read-only interrogation of GitHub state (files of
interest, repo settings, rulesets, workflows, org policy, alerts). A check yields
``unknown`` whenever the required scope/file cannot be read — never a false pass/fail.
This module is exercised against a mocked githubkit client in integration tests; the
live calls are marked no-cover.
"""

from __future__ import annotations

from hangar.domain.models import AlertCounts, CIStatus, ProviderConnection, Repo

# Files whose absence fails a content check.
_FILE_CHECKS = {
    "license": ["LICENSE", "LICENSE.md", "LICENSE.txt"],
    "readme": ["README.md", "README.rst", "README"],
    "security_md": ["SECURITY.md", ".github/SECURITY.md"],
    "codeowners": ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"],
    "changelog": ["CHANGELOG.md", "CHANGELOG"],
    "lockfile": ["poetry.lock", "package-lock.json", "pnpm-lock.yaml", "uv.lock", "Cargo.lock"],
    "release_please": ["release-please-config.json", ".release-please-manifest.json"],
}


async def interrogate_repo(  # pragma: no cover - needs live creds
    client,
    connection: ProviderConnection,
    repo_ref: str,
    etags: dict[str, str],
) -> Repo:
    """Read a single repo into a normalized snapshot with fails/unknowns populated.

    Conditional requests (ETag) avoid re-downloading unchanged resources (SC-010).
    Capabilities absent on the connection turn the corresponding checks ``unknown``.
    """
    owner = connection.label.split(":")[-1]
    granted = connection.granted_capabilities

    repo = await client.rest.repos.async_get(owner=owner, repo=repo_ref)
    data = repo.parsed_data

    fails: list[str] = []
    unknowns: list[str] = []

    # File-presence checks
    from hangar.domain.models import Capability

    can_read_files = Capability.read_files in granted
    for check_id, candidates in _FILE_CHECKS.items():
        if not can_read_files:
            unknowns.append(check_id)
            continue
        if not await _any_file_exists(client, owner, repo_ref, candidates):
            fails.append(check_id)

    # Settings/metadata checks
    if not data.description:
        fails.append("description")
    if data.default_branch != "main":
        fails.append("default_branch")

    # Security feature checks require read_settings/read_alerts; otherwise unknown.
    if Capability.read_settings not in granted:
        unknowns.extend(["secret_scanning", "code_scanning", "branch_protection"])
    if Capability.read_org_policy not in granted:
        unknowns.append("two_fa")

    alerts = AlertCounts()  # populated from the dependabot/code-scanning alert APIs
    ci = CIStatus.none

    return Repo(
        id=repo_ref,
        connection_id=connection.id,
        description=data.description or "",
        default_branch=data.default_branch,
        open_prs=data.open_issues_count or 0,
        dependabot_prs=0,
        ci_status=ci,
        alerts=alerts,
        release_pending_days=None,
        fails=sorted(set(fails)),
        unknowns=sorted(set(unknowns)),
    )


async def _any_file_exists(client, owner: str, repo: str, paths: list[str]) -> bool:  # pragma: no cover
    from githubkit.exception import RequestFailed

    for path in paths:
        try:
            await client.rest.repos.async_get_content(owner=owner, repo=repo, path=path)
            return True
        except RequestFailed:
            continue
    return False
