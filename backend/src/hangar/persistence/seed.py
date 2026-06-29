"""Prototype fixture data — the exact CONNECTIONS / REPOS / audit seed from
``docs/prototype/Hangar.dc.html``.

Seeding on first boot lets Hangar render identically to the normative prototype and
gives the test suites deterministic data without a live GitHub. Real connections added
via the Providers screen are interrogated by the adapters and overwrite/augment this.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TypedDict

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

class _Conn(TypedDict):
    id: str
    label: str
    provider_type: str
    scope: str
    auth_mode: str
    caps: list[Capability]
    sync: str


class _Alerts(TypedDict):
    c: int
    h: int
    m: int
    l: int  # noqa: E741 - mirrors the prototype fixture key (severity "low")


class _Repo(TypedDict):
    id: str
    conn: str
    desc: str
    openPRs: int
    depPRs: int
    ci: str
    alerts: _Alerts
    rel: int | None
    fails: list[str]
    unknowns: list[str]


class _Audit(TypedDict):
    t: str
    repo: str
    check: str
    conn: str
    result: str


CONNECTIONS: list[_Conn] = [
    dict(id="gh-main", label="gh:get2knowio", provider_type="github", scope="org · 9 repos",
         auth_mode="GitHub App #4471", caps=_WRITE_CAPS, sync="2m ago"),
    dict(id="gh-labs", label="gh:get2know-labs", provider_type="github", scope="org · 3 repos",
         auth_mode="GitHub App #4471", caps=_WRITE_CAPS, sync="6m ago"),
    dict(id="gitea", label="gitea:homelab", provider_type="gitea", scope="user · 2 repos",
         auth_mode="Scoped token", caps=_READ_CAPS, sync="12m ago"),
]

REPOS: list[_Repo] = [
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

AUDIT: list[_Audit] = [
    dict(t="4m ago", repo="get2know-web", check="Description & topics set", conn="gh:get2knowio", result="Settings applied"),
    dict(t="1h ago", repo="ntfy-bridge", check="LICENSE present", conn="gh:get2knowio", result="PR #138 merged"),
    dict(t="yesterday", repo="hola", check="Dependabot alerts", conn="gh:get2knowio", result="Settings applied"),
]


def _ago(text: str) -> timedelta:
    """Turn a prototype display string ('2m ago' / '1h ago' / 'yesterday') into a real
    timedelta. The demo then seeds honest, *aging* timestamps (rendered back through
    ``format_relative``) instead of frozen hardcoded strings (Constitution VIII)."""
    text = text.strip().lower()
    if text == "yesterday":
        return timedelta(hours=26)
    token = text.split()[0]  # "12m", "1h", "3d"
    try:
        value, unit = int(token[:-1]), token[-1]
    except ValueError:
        return timedelta()
    return {"m": timedelta(minutes=value), "h": timedelta(hours=value),
            "d": timedelta(days=value)}.get(unit, timedelta())


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
                # Real, staggered sync times (computed from the fixture's relative offset)
                # so the demo shows honest, aging "synced …" values, not frozen strings.
                last_sync_at=now - _ago(c["sync"]), created_at=now,
            )
        )
    for r in REPOS:
        a = r["alerts"]
        session.add(
            RepoRow(
                id=r["id"], connection_id=r["conn"], description=r["desc"],
                default_branch="main", open_prs=r["openPRs"], bot_prs=r["depPRs"],
                ci_status=r["ci"],
                alerts={"critical": a["c"], "high": a["h"], "moderate": a["m"], "low": a["l"]},
                release_pending_days=r["rel"], fails=r["fails"], unknowns=r["unknowns"],
                last_evaluated_at=now,
            )
        )
    for entry in AUDIT:
        session.add(
            AuditRow(
                timestamp=now - _ago(entry["t"]), connection_label=entry["conn"], actor="paul",
                repo_id=entry["repo"], check_label=entry["check"], result=entry["result"],
                pr_url=None,
            )
        )
    if await session.get(PolicyRow, "default") is None:
        p = default_policy()
        session.add(PolicyRow(id=p.id, name=p.name, entries=[e.model_dump() for e in p.entries]))

    await session.commit()
    return True
