"""Fleet overview aggregation (FR-001–FR-004; prototype ``statTiles``/``repoRows``/``feed``).

Produces the six stat tiles, the repo table rows, and the urgency-sorted attention feed
for a connection filter. Pure transformation over cached snapshots — no live calls.
"""

from __future__ import annotations

from hangar.domain.models import (
    CIStatus,
    Policy,
    ProviderConnection,
    Repo,
    Tone,
)
from hangar.domain.policy import RemediationMap, hygiene, hygiene_tone


def _badge_after_colon(label: str) -> str:
    parts = label.split(":")
    return parts[1] if len(parts) > 1 else label


def build_overview(
    repos: list[Repo],
    connections: dict[str, ProviderConnection],
    policy: Policy,
    remediations: RemediationMap,
    *,
    synced: str,
) -> dict:
    def s(fn) -> int:
        return sum(fn(r) for r in repos)

    open_prs = s(lambda r: r.open_prs)
    dep_prs = s(lambda r: r.dependabot_prs)
    ci_fail = sum(1 for r in repos if r.ci_status is CIStatus.fail)
    crit = s(lambda r: r.alerts.critical)
    alerts_total = s(lambda r: r.alerts.total)
    rel_pending = sum(1 for r in repos if r.release_pending_days is not None)
    # Hygiene once per repo, reused for the compliance average and the per-row bar.
    hyg = {r.id: hygiene(r, policy, remediations) for r in repos}
    compliance = round(sum(hyg.values()) / len(repos)) if repos else 100

    stats = [
        {"label": "Open PRs", "value": str(open_prs), "sub": f"{dep_prs} Dependabot", "tone": Tone.neutral},
        {"label": "Bot PRs", "value": str(dep_prs), "sub": "awaiting merge", "tone": Tone.neutral},
        {"label": "CI failing", "value": str(ci_fail), "sub": "on default", "tone": Tone.fail if ci_fail else Tone.neutral},
        {"label": "Sec alerts", "value": str(alerts_total), "sub": f"{crit} critical", "tone": Tone.fail if crit else Tone.neutral},
        {"label": "Release pending", "value": str(rel_pending), "sub": "unreleased", "tone": Tone.neutral},
        {"label": "Compliance", "value": f"{compliance}%", "sub": "fleet avg", "tone": hygiene_tone(compliance)},
    ]

    repo_rows = []
    for r in repos:
        conn = connections.get(r.connection_id)
        badge = _badge_after_colon(conn.label) if conn else r.connection_id
        a = r.alerts
        repo_rows.append({
            "id": r.id,
            "connection_badge": badge,
            "description": r.description,
            "open_prs": r.open_prs,
            "dependabot_prs": r.dependabot_prs,
            "ci": r.ci_status.value,
            "alerts_total": a.total,
            "alerts_tone": Tone.fail if a.critical else (Tone.warn if a.high else Tone.neutral),
            "release_pending_days": r.release_pending_days,
            "hygiene_pct": hyg[r.id],
        })

    feed = _build_feed(repos)

    return {
        "summary": {
            "repo_count": len(repos),
            "compliance_pct": compliance,
            "synced": synced,
            # Structured signals for the sidebar urgency badge — never re-parsed from a
            # display string (FR-001).
            "ci_failing": ci_fail,
            "critical_alerts": crit,
        },
        "stats": stats,
        "repos": repo_rows,
        "feed": feed,
    }


def _build_feed(repos: list[Repo]) -> list[dict]:
    """Attention feed: critical → CI → release → high-alert → bot PRs (prototype order)."""
    ranked: list[tuple[int, dict]] = []
    for r in repos:
        if r.alerts.critical > 0:
            n = r.alerts.critical
            ranked.append((0, {"tag": "Critical", "tone": Tone.fail, "repo_id": r.id,
                               "title": f"{n} critical security alert{'s' if n > 1 else ''}"}))
    for r in repos:
        if r.ci_status is CIStatus.fail:
            ranked.append((1, {"tag": "CI down", "tone": Tone.fail, "repo_id": r.id,
                               "title": "CI failing on default branch"}))
    for r in repos:
        if r.release_pending_days is not None and r.release_pending_days >= 14:
            ranked.append((2, {"tag": "Release", "tone": Tone.warn, "repo_id": r.id,
                               "title": f"{r.release_pending_days}d of unreleased commits"}))
    for r in repos:
        if r.alerts.high > 0:
            n = r.alerts.high
            ranked.append((3, {"tag": "High alert", "tone": Tone.warn, "repo_id": r.id,
                               "title": f"{n} high-severity alert{'s' if n > 1 else ''}"}))
    for r in repos:
        if r.dependabot_prs >= 2:
            ranked.append((4, {"tag": "Bot PRs", "tone": Tone.neutral, "repo_id": r.id,
                               "title": f"{r.dependabot_prs} Dependabot PRs awaiting merge"}))
    ranked.sort(key=lambda t: t[0])
    return [item for _, item in ranked[:7]]
