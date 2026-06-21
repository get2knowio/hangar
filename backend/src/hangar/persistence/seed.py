"""Prototype fixture data — the exact CONNECTIONS / REPOS / audit seed from
``docs/prototype/Hangar.dc.html``.

Seeding on first boot lets Hangar render identically to the normative prototype and
gives the test suites deterministic data without a live GitHub. Real connections added
via the Providers screen are interrogated by the adapters and overwrite/augment this.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.domain.models import Capability
from hangar.domain.policy import default_policy
from hangar.persistence.models import AuditRow, ConnectionRow, PolicyRow, RepoRow

_WRITE_CAPS = [
    Capability.read_settings, Capability.read_files, Capability.read_alerts,
    Capability.read_org_policy, Capability.write_settings, Capability.open_pull_request,
    Capability.deep_link, Capability.subscribe_webhooks,
]
_READ_CAPS = [
    Capability.read_settings, Capability.read_files, Capability.read_alerts,
    Capability.deep_link,
]

CONNECTIONS = [
    dict(id="gh-main", label="gh:get2knowio", provider_type="github", scope="org · 9 repos",
         auth_mode="GitHub App #4471", caps=_WRITE_CAPS, sync="2m ago"),
    dict(id="gh-labs", label="gh:get2know-labs", provider_type="github", scope="org · 3 repos",
         auth_mode="GitHub App #4471", caps=_WRITE_CAPS, sync="6m ago"),
    dict(id="gitea", label="gitea:homelab", provider_type="gitea", scope="user · 2 repos",
         auth_mode="Scoped token", caps=_READ_CAPS, sync="12m ago"),
]

REPOS = [
    dict(id="hola", conn="gh-main", desc="Homelab Compose deployer CLI", openPRs=4, depPRs=2, ci="pass", alerts=dict(c=0, h=0, m=1, l=2), rel=None, fails=["two_fa"], unknowns=[]),
    dict(id="hangar", conn="gh-main", desc="Fleet control plane (this app)", openPRs=6, depPRs=3, ci="fail", alerts=dict(c=1, h=1, m=0, l=0), rel=9, fails=["cooldown", "license", "branch_protection", "code_scanning", "conventional"], unknowns=["two_fa"]),
    dict(id="get2know-web", conn="gh-main", desc="Marketing & docs site", openPRs=2, depPRs=1, ci="pass", alerts=dict(c=0, h=0, m=0, l=1), rel=3, fails=["security_md", "templates"], unknowns=["two_fa"]),
    dict(id="conventional-bot", conn="gh-main", desc="Commit-lint GitHub App", openPRs=1, depPRs=0, ci="pass", alerts=dict(c=0, h=1, m=0, l=0), rel=None, fails=["license", "changelog"], unknowns=["dep_review"]),
    dict(id="homelab-compose", conn="gh-main", desc="Traefik + services stack", openPRs=3, depPRs=2, ci="fail", alerts=dict(c=0, h=0, m=2, l=1), rel=21, fails=["cooldown", "dependabot_updates", "branch_protection"], unknowns=[]),
    dict(id="release-please-config", conn="gh-main", desc="Shared release config", openPRs=0, depPRs=0, ci="pass", alerts=dict(c=0, h=0, m=0, l=0), rel=None, fails=["two_fa"], unknowns=[]),
    dict(id="dotfiles", conn="gh-main", desc="Personal shell + editor config", openPRs=0, depPRs=0, ci="none", alerts=dict(c=0, h=0, m=0, l=0), rel=None, fails=["license", "security_md", "codeowners", "dependabot_updates", "branch_protection"], unknowns=["code_scanning", "secret_scanning"]),
    dict(id="ntfy-bridge", conn="gh-main", desc="Notification fan-out worker", openPRs=2, depPRs=1, ci="pass", alerts=dict(c=0, h=0, m=1, l=0), rel=5, fails=["cooldown", "changelog"], unknowns=["two_fa"]),
    dict(id="traefik-conf", conn="gh-main", desc="Edge routing rules", openPRs=1, depPRs=0, ci="none", alerts=dict(c=0, h=0, m=0, l=0), rel=None, fails=["license", "readme", "description"], unknowns=[]),
    dict(id="scorecard-exp", conn="gh-labs", desc="OSSF Scorecard spike", openPRs=1, depPRs=1, ci="pass", alerts=dict(c=0, h=0, m=1, l=0), rel=None, fails=["license", "security_md", "codeowners", "branch_protection"], unknowns=["two_fa"]),
    dict(id="webhook-lab", conn="gh-labs", desc="Webhook receiver experiments", openPRs=2, depPRs=1, ci="fail", alerts=dict(c=0, h=1, m=0, l=0), rel=14, fails=["cooldown"], unknowns=[]),
    dict(id="plex-grotesk", conn="gh-labs", desc="Type tokens playground", openPRs=0, depPRs=0, ci="pass", alerts=dict(c=0, h=0, m=0, l=1), rel=None, fails=["license", "description", "templates"], unknowns=[]),
    dict(id="backup-scripts", conn="gitea", desc="Restic backup cron", openPRs=0, depPRs=0, ci="none", alerts=dict(c=0, h=0, m=0, l=0), rel=None, fails=["license", "branch_protection", "cooldown"], unknowns=["secret_scanning", "code_scanning", "dep_review"]),
    dict(id="lan-dns", conn="gitea", desc="Internal DNS records", openPRs=1, depPRs=0, ci="pass", alerts=dict(c=0, h=0, m=0, l=0), rel=None, fails=["readme", "license"], unknowns=["secret_scanning", "code_scanning"]),
]

AUDIT = [
    dict(t="4m ago", repo="get2know-web", check="Description & topics set", conn="gh:get2knowio", result="Settings applied"),
    dict(t="1h ago", repo="ntfy-bridge", check="LICENSE present", conn="gh:get2knowio", result="PR #138 merged"),
    dict(t="yesterday", repo="hola", check="Dependabot alerts", conn="gh:get2knowio", result="Settings applied"),
]


async def seed_if_empty(session: AsyncSession) -> bool:
    """Idempotent: populate fixtures only when the connections table is empty.

    Returns True if seeding happened.
    """
    count = (await session.execute(select(func.count()).select_from(ConnectionRow))).scalar() or 0
    if count:
        return False

    now = datetime.now(UTC)
    for c in CONNECTIONS:
        session.add(
            ConnectionRow(
                id=c["id"], label=c["label"], provider_type=c["provider_type"],
                scope=c["scope"], auth_mode=c["auth_mode"],
                granted_capabilities=[cap.value for cap in c["caps"]],
                last_sync_at=now, created_at=now,
            )
        )
    for r in REPOS:
        a = r["alerts"]
        session.add(
            RepoRow(
                id=r["id"], connection_id=r["conn"], description=r["desc"],
                default_branch="main", open_prs=r["openPRs"], dependabot_prs=r["depPRs"],
                ci_status=r["ci"],
                alerts={"critical": a["c"], "high": a["h"], "moderate": a["m"], "low": a["l"]},
                release_pending_days=r["rel"], fails=r["fails"], unknowns=r["unknowns"],
                last_evaluated_at=now,
            )
        )
    for entry in AUDIT:
        session.add(
            AuditRow(
                timestamp=now, connection_label=entry["conn"], actor="paul",
                repo_id=entry["repo"], check_label=entry["check"], result=entry["result"],
                pr_url=None,
            )
        )
    if await session.get(PolicyRow, "default") is None:
        p = default_policy()
        session.add(PolicyRow(id=p.id, name=p.name, entries=[e.model_dump() for e in p.entries]))

    await session.commit()
    return True
