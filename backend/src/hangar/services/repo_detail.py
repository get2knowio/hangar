"""Repo drill-down presenter (FR-005a, Story 3; prototype ``buildCtl`` + ``prList``).

Produces the RepoDetail contract: header, activity strip (CI, alerts, and — for
credential-less demo connections only — the prototype's illustrative PR list) and grouped
policy checks each carrying its resolved remediation control (structured kind, action
labels, evidence, open-PR overlay).
"""

from __future__ import annotations

from datetime import UTC, datetime

from hangar.domain.checks import GROUPS
from hangar.domain.models import (
    FindingStatus,
    Policy,
    ProviderConnection,
    RemediationTier,
    Repo,
    Tone,
    kind_for_tier,
    tier_label,
)
from hangar.domain.policy import (
    RemediationMap,
    effective_status,
    enabled_checks,
    evidence_for,
    hygiene,
    pass_count,
)
from hangar.providers.base import provider_name

_DEP_TITLES = ["actions/checkout to v4.2", "vite to 5.4.8", "fastapi to 0.115",
               "pydantic to 2.9", "ruff to 0.6.9"]
_HUMAN_TITLES = ["Refactor poller cadence", "Add /health endpoint",
                 "Fix webhook retry backoff", "Docs: homelab deploy guide"]


def _relative_age(iso: str | None) -> str:
    """Compact age ("3d"/"5h"/"12m") from an ISO timestamp; "" when absent/unparseable."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    secs = int((datetime.now(UTC) - dt).total_seconds())
    if secs < 3600:
        return f"{max(secs // 60, 0)}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def _pr_list(repo: Repo, *, synthesize: bool) -> list[dict]:
    """Per-PR rows for the activity strip.

    Prefers the real open PRs the poller captured into the snapshot. For a credential-less
    demo connection with no captured PRs we keep the prototype's illustrative list so the
    offline demo renders as designed; for a live connection with none we return no rows
    (honest state) — the header still shows the true open-PR count.
    """
    if repo.pull_requests:
        return [
            {
                "title": pr.title,
                "kind": pr.kind,
                "status": "draft" if pr.draft else "open",
                "status_tone": (Tone.warn if pr.draft else Tone.neutral).value,
                "age": _relative_age(pr.created_at),
                "url": pr.url,
            }
            for pr in repo.pull_requests
        ]
    if not synthesize:
        return []
    prs: list[dict] = []
    for i in range(repo.bot_prs):
        cooldown = i == 0
        prs.append({
            "title": f"Bump {_DEP_TITLES[i % len(_DEP_TITLES)]}",
            "kind": "dependabot",
            "status": "cooldown 4d" if cooldown else "ready",
            "status_tone": (Tone.warn if cooldown else Tone.passing).value,
            "age": f"{i + 1}d",
        })
    for i in range(max(0, repo.open_prs - repo.bot_prs)):
        prs.append({
            "title": _HUMAN_TITLES[i % len(_HUMAN_TITLES)],
            "kind": "human",
            "status": "in review",
            "status_tone": Tone.neutral.value,
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


def build_repo_detail(
    repo: Repo,
    connection: ProviderConnection,
    policy: Policy,
    remediations: RemediationMap,
    rem_pr_urls: dict[tuple[str, str, str], str | None],
    rem_pr_numbers: dict[tuple[str, str, str], int | None],
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
            key = (repo.connection_id, repo.id, c.id)
            pending = status is FindingStatus.pending
            group_checks.append({
                "id": c.id,
                "label": c.label,
                "status": status.value,
                # Structured remediation kind the client sends back — the UI must not
                # reverse-engineer it from the action label (Constitution VII).
                "kind": kind_for_tier(tier).value,
                "tier_label": tier_label(tier),
                "evidence": evidence_for(repo, c.id, status),
                "open_pr_url": rem_pr_urls.get(key) if pending else None,
                "open_pr_number": rem_pr_numbers.get(key) if pending else None,
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
        "pull_requests": _pr_list(repo, synthesize=not connection.has_credential),
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
        return f"Open in {provider_name(provider_type)} ↗", None
    if tier is RemediationTier.patch:
        return "Enable", None
    if tier is RemediationTier.pr:
        return "Open fix PR", None
    return None, None  # defensive default for any future tier not handled above
