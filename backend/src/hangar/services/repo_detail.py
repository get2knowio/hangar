"""Repo drill-down presenter (FR-005a, Story 3; prototype ``buildCtl`` + ``prList``).

Produces the RepoDetail contract: header, activity strip (synthetic PR list matching the
prototype, CI, alerts) and grouped policy checks each carrying its resolved remediation
control (primary/secondary action labels, evidence, open-PR overlay).
"""

from __future__ import annotations

from hangar.domain.checks import GROUPS
from hangar.domain.models import (
    FindingStatus,
    Policy,
    ProviderConnection,
    RemediationTier,
    Repo,
)
from hangar.domain.policy import (
    RemediationMap,
    effective_status,
    enabled_checks,
    evidence_for,
    hygiene,
    pass_count,
)

_DEP_TITLES = ["actions/checkout to v4.2", "vite to 5.4.8", "fastapi to 0.115",
               "pydantic to 2.9", "ruff to 0.6.9"]
_HUMAN_TITLES = ["Refactor poller cadence", "Add /health endpoint",
                 "Fix webhook retry backoff", "Docs: homelab deploy guide"]


def _pr_list(repo: Repo) -> list[dict]:
    prs: list[dict] = []
    for i in range(repo.dependabot_prs):
        prs.append({
            "title": f"Bump {_DEP_TITLES[i % len(_DEP_TITLES)]}",
            "kind": "dependabot",
            "status": "cooldown 4d" if i == 0 else "ready",
            "age": f"{i + 1}d",
        })
    for i in range(max(0, repo.open_prs - repo.dependabot_prs)):
        prs.append({
            "title": _HUMAN_TITLES[i % len(_HUMAN_TITLES)],
            "kind": "human",
            "status": "in review",
            "age": f"{i + 2}d",
        })
    return prs


def _alerts(repo: Repo) -> list[dict]:
    a = repo.alerts
    out = []
    if a.critical:
        out.append({"severity": "critical", "count": a.critical})
    if a.high:
        out.append({"severity": "high", "count": a.high})
    if a.moderate:
        out.append({"severity": "moderate", "count": a.moderate})
    if a.low:
        out.append({"severity": "low", "count": a.low})
    return out


_TIER_LABEL = {
    RemediationTier.patch: "API",
    RemediationTier.pr: "API · PR",
    RemediationTier.link: "Deep-link",
    RemediationTier.report: "Report",
}


def build_repo_detail(
    repo: Repo,
    connection: ProviderConnection,
    policy: Policy,
    remediations: RemediationMap,
    rem_pr_urls: dict[tuple[str, str], str | None],
) -> dict:
    checks = enabled_checks(policy)
    hyg = hygiene(repo, policy, remediations)
    pc = pass_count(repo, policy, remediations)
    read_only = not connection.writes

    groups = []
    for g in GROUPS:
        group_checks = []
        for c in (x for x in checks if x.group == g):
            status = effective_status(repo, c.id, remediations)
            tier = c.tier_for(connection.granted_capabilities)
            primary, secondary = _actions(status, tier, connection.provider_type)
            open_pr = rem_pr_urls.get((repo.id, c.id)) if status is FindingStatus.pending else None
            group_checks.append({
                "id": c.id,
                "label": c.label,
                "status": status.value,
                "tier_label": _TIER_LABEL[tier],
                "evidence": evidence_for(repo, c.id, status),
                "open_pr_url": open_pr,
                "primary_action": primary,
                "secondary_action": secondary,
            })
        if group_checks:
            groups.append({"group": g, "checks": group_checks})

    ci = repo.ci_status.value
    return {
        "id": repo.id,
        "connection_label": connection.label,
        "description": repo.description,
        "read_only": read_only,
        "hygiene_pct": hyg,
        "pass_count": f"{pc}/{len(checks)} checks",
        "open_prs": repo.open_prs,
        "ci": ci,
        "pull_requests": _pr_list(repo),
        "alerts": _alerts(repo),
        "check_groups": groups,
    }


def _actions(
    status: FindingStatus, tier: RemediationTier, provider_type: str
) -> tuple[str | None, str | None]:
    """Resolve primary/secondary action labels (prototype ``buildCtl``)."""
    if status in (FindingStatus.passing, FindingStatus.working):
        return None, None
    if status is FindingStatus.pending:
        return None, "Mark merged"
    # fail / unknown
    if tier is RemediationTier.report:
        return None, None
    if tier is RemediationTier.link:
        return f"Open in {_provider_name(provider_type)} ↗", None
    if tier is RemediationTier.patch:
        return "Enable", None
    if tier is RemediationTier.pr:
        return "Open fix PR", None
    return None, None


def _provider_name(provider_type: str) -> str:
    return {"github": "GitHub", "gitea": "Gitea"}.get(provider_type, provider_type.title())
