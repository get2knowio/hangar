"""GitHub detection heuristics (research.md §11) — real, read-only interrogation.

Each catalog check maps to a live GitHub read (repo metadata, contents API, rulesets,
org policy, alerts). The primary repo resource is fetched conditionally (If-None-Match);
a ``304`` returns ``None`` so the poller keeps the cached snapshot (SC-010). A check
whose required capability/scope is absent — or whose resource returns 403 — yields
``unknown`` rather than a false pass/fail.
"""

from __future__ import annotations

from hangar.domain.models import AlertCounts, Capability, CIStatus, ProviderConnection, Repo

# Candidate paths whose presence satisfies a file-based check. (license is determined
# from repo metadata below — GitHub's own license detection — not a filename match.)
_FILE_CHECKS = {
    "readme": ["README.md", "README.rst", "README"],
    "security_md": ["SECURITY.md", ".github/SECURITY.md"],
    "codeowners": ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"],
    "changelog": ["CHANGELOG.md", "CHANGELOG"],
    "lockfile": ["poetry.lock", "package-lock.json", "pnpm-lock.yaml", "uv.lock", "Cargo.lock"],
    "release_please": ["release-please-config.json", ".release-please-manifest.json"],
    "templates": [".github/ISSUE_TEMPLATE/config.yml", ".github/ISSUE_TEMPLATE",
                  ".github/PULL_REQUEST_TEMPLATE.md"],
    "dependabot_updates": [".github/dependabot.yml", ".github/dependabot.yaml"],
}


async def interrogate_repo(adapter, gh, connection: ProviderConnection, repo_ref: str) -> Repo | None:
    """Interrogate one repo. Returns a normalized snapshot, or None if unchanged (304)."""
    from hangar.providers.github.adapter import _NOT_FOUND, _NOT_MODIFIED

    owner = connection.owner
    granted = connection.granted_capabilities
    cget = adapter._conditional_get

    repo_data = await cget(gh, connection.id, f"/repos/{owner}/{repo_ref}")
    if repo_data is _NOT_MODIFIED:
        return None  # snapshot unchanged since the last poll — keep the cache
    if repo_data is _NOT_FOUND:
        return None

    fails: list[str] = []
    unknowns: list[str] = []

    can_files = Capability.read_files in granted
    can_settings = Capability.read_settings in granted
    can_alerts = Capability.read_alerts in granted
    can_org = Capability.read_org_policy in granted

    # --- file-presence checks (contents API; 404 = absent) ---
    async def _present(path: str) -> bool:
        r = await cget(gh, connection.id, f"/repos/{owner}/{repo_ref}/contents/{path}")
        return r is not _NOT_FOUND  # 200 or 304 (exists, unchanged) → present

    for check_id, candidates in _FILE_CHECKS.items():
        if not can_files:
            unknowns.append(check_id)
            continue
        present = False
        for path in candidates:
            if await _present(path):
                present = True
                break
        if not present:
            fails.append(check_id)

    # cooldown: dependabot.yml must contain a cooldown block (requires reading content)
    if can_files:
        if "dependabot_updates" in fails:
            fails.append("cooldown")  # no dependabot.yml at all
        else:
            content = await _read_text(cget, gh, connection.id, owner, repo_ref, ".github/dependabot.yml")
            if content is None or "cooldown" not in content:
                fails.append("cooldown")
    else:
        unknowns.append("cooldown")

    # --- repo-metadata checks ---
    if not repo_data.get("license"):
        fails.append("license")
    if not (repo_data.get("description") and repo_data.get("topics")):
        fails.append("description")
    if repo_data.get("default_branch") != "main":
        fails.append("default_branch")

    # secret scanning is in security_and_analysis (admin-visible)
    saa = repo_data.get("security_and_analysis")
    if saa is not None:
        ss = (saa.get("secret_scanning") or {}).get("status")
        pp = (saa.get("secret_scanning_push_protection") or {}).get("status")
        if ss != "enabled" or pp != "enabled":
            fails.append("secret_scanning")
    elif can_settings:
        fails.append("secret_scanning")  # readable but field absent → not enabled
    else:
        unknowns.append("secret_scanning")

    default_branch = repo_data.get("default_branch", "main")

    # --- settings/ruleset checks ---
    if can_settings:
        prot = await cget(gh, connection.id, f"/repos/{owner}/{repo_ref}/branches/{default_branch}/protection")
        if prot is _NOT_FOUND:
            fails.append("branch_protection")
        elif prot is _NOT_MODIFIED:
            pass  # protection exists, unchanged
        wf_perms = await cget(gh, connection.id, f"/repos/{owner}/{repo_ref}/actions/permissions/workflow")
        if isinstance(wf_perms, dict):
            if wf_perms.get("default_workflow_permissions") != "read":
                fails.append("workflow_permissions")
        elif wf_perms is _NOT_FOUND:
            fails.append("workflow_permissions")
        cs = await cget(gh, connection.id, f"/repos/{owner}/{repo_ref}/code-scanning/analyses")
        if cs is _NOT_FOUND:
            fails.append("code_scanning")
    else:
        unknowns.extend(["branch_protection", "workflow_permissions", "code_scanning"])

    # org 2FA enforcement (org policy scope)
    if can_org:
        org = await cget(gh, connection.id, f"/orgs/{owner}")
        if isinstance(org, dict) and not org.get("two_factor_requirement_enabled"):
            fails.append("two_fa")
        elif org is _NOT_FOUND:
            unknowns.append("two_fa")
    else:
        unknowns.append("two_fa")

    # dep_review / conventional / actions_pinned_sha require deep workflow-file parsing
    # we don't do in a single read; report unknown rather than a false pass (research §11),
    # regardless of read_files scope.
    unknowns.extend(["dep_review", "conventional", "actions_pinned_sha"])

    # --- activity signals ---
    open_prs, dependabot_prs = await _pull_counts(cget, gh, connection.id, owner, repo_ref)
    ci = await _ci_status(cget, gh, connection.id, owner, repo_ref, default_branch)
    if ci is CIStatus.fail:
        fails.append("ci_workflow_green")
    elif ci is CIStatus.none:
        unknowns.append("ci_workflow_green")
    alerts = await _alert_counts(cget, gh, connection.id, owner, repo_ref) if can_alerts else AlertCounts()

    return Repo(
        id=repo_ref,
        connection_id=connection.id,
        description=repo_data.get("description") or "",
        default_branch=default_branch,
        open_prs=open_prs,
        dependabot_prs=dependabot_prs,
        ci_status=ci,
        alerts=alerts,
        release_pending_days=None,
        fails=sorted(set(fails)),
        unknowns=sorted(set(unknowns) - set(fails)),
    )


async def _read_text(cget, gh, cid, owner, repo, path) -> str | None:
    import base64

    from hangar.providers.github.adapter import _NOT_FOUND, _NOT_MODIFIED

    data = await cget(gh, cid, f"/repos/{owner}/{repo}/contents/{path}")
    if data in (_NOT_FOUND, _NOT_MODIFIED) or not isinstance(data, dict):
        return None
    if data.get("encoding") == "base64" and data.get("content"):
        try:
            return base64.b64decode(data["content"]).decode("utf-8", "replace")
        except ValueError:
            return None
    return None


async def _pull_counts(cget, gh, cid, owner, repo) -> tuple[int, int]:
    from hangar.providers.github.adapter import _NOT_FOUND, _NOT_MODIFIED

    data = await cget(gh, cid, f"/repos/{owner}/{repo}/pulls", {"state": "open", "per_page": 100})
    if not isinstance(data, list):
        return (0, 0) if data in (_NOT_FOUND, _NOT_MODIFIED) else (0, 0)
    dependabot = sum(1 for pr in data if (pr.get("user") or {}).get("login") in
                     ("dependabot[bot]", "dependabot-preview[bot]"))
    return len(data), dependabot


async def _ci_status(cget, gh, cid, owner, repo, branch) -> CIStatus:

    data = await cget(gh, cid, f"/repos/{owner}/{repo}/actions/runs",
                      {"branch": branch, "per_page": 1})
    if not isinstance(data, dict):
        return CIStatus.none
    runs = data.get("workflow_runs") or []
    if not runs:
        return CIStatus.none
    conclusion = runs[0].get("conclusion")
    if conclusion == "success":
        return CIStatus.passing
    if conclusion in ("failure", "timed_out", "cancelled"):
        return CIStatus.fail
    return CIStatus.none


async def _alert_counts(cget, gh, cid, owner, repo) -> AlertCounts:
    data = await cget(gh, cid, f"/repos/{owner}/{repo}/dependabot/alerts", {"state": "open", "per_page": 100})
    if not isinstance(data, list):
        return AlertCounts()
    counts = {"critical": 0, "high": 0, "moderate": 0, "low": 0}
    for alert in data:
        sev = ((alert.get("security_advisory") or {}).get("severity")
               or (alert.get("security_vulnerability") or {}).get("severity"))
        if sev in counts:
            counts[sev] += 1
    return AlertCounts(**counts)
