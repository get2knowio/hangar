"""Provider-neutral domain model (Constitution I).

These types speak PRD vocabulary only — *connection*, *repo*, *check*, *finding*,
*remediation*, *capability* — and never branch on a platform. Adapters in
``hangar.providers`` translate platform specifics into these shapes; the domain,
services and API are written against them so adding Gitea is a new adapter, not a
core change. Persistence ORM rows (``hangar.persistence.models``) mirror a subset of
these and convert to/from them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


# --------------------------------------------------------------------------- enums
class Capability(StrEnum):
    """Provider-declared ability a Check references to resolve its tier (FR-010)."""

    read_settings = "read_settings"
    read_files = "read_files"
    read_alerts = "read_alerts"
    read_org_policy = "read_org_policy"
    write_settings = "write_settings"
    open_pull_request = "open_pull_request"
    deep_link = "deep_link"
    subscribe_webhooks = "subscribe_webhooks"


class RemediationTier(StrEnum):
    patch = "patch"          # scoped settings PATCH
    pr = "pr"                # config change delivered as a PR (never push)
    link = "link"            # deep-link to the provider UI
    report = "report"        # surface only


# Canonical tier → UI badge label (single source of truth; matches the prototype).
TIER_LABELS: dict[RemediationTier, str] = {
    RemediationTier.patch: "API",
    RemediationTier.pr: "API · PR",
    RemediationTier.link: "Deep-link",
    RemediationTier.report: "Report",
}


def tier_label(tier: RemediationTier) -> str:
    return TIER_LABELS[tier]


class RemediationKind(StrEnum):
    report = "report"
    deep_link = "deep_link"
    settings_patch = "settings_patch"
    config_pr = "config_pr"


# Canonical effective-tier → remediation-kind map (single source of truth, used by the
# remediation service, the remediate endpoint, and the repo-detail presenter).
_TIER_TO_KIND: dict[RemediationTier, RemediationKind] = {
    RemediationTier.patch: RemediationKind.settings_patch,
    RemediationTier.pr: RemediationKind.config_pr,
    RemediationTier.link: RemediationKind.deep_link,
    RemediationTier.report: RemediationKind.report,
}


def kind_for_tier(tier: RemediationTier) -> RemediationKind:
    return _TIER_TO_KIND[tier]


class RemediationState(StrEnum):
    working = "working"
    pr_open = "pr_open"
    fixed = "fixed"
    deep_link = "deep_link"


class FindingStatus(StrEnum):
    """Effective status incl. remediation overlay (FR-005, FR-005a; prototype ``effStatus``)."""

    passing = "pass"
    fail = "fail"
    unknown = "unknown"
    pending = "pending"      # a Hangar-authored PR is open for this finding
    working = "working"      # correction submitting
    suppressed = "suppressed"  # opted out for this repo via .hangar.json — not scored


class CIStatus(StrEnum):
    passing = "pass"
    fail = "fail"
    none = "none"


class Tone(StrEnum):
    passing = "pass"
    warn = "warn"
    fail = "fail"
    unknown = "unknown"
    neutral = "neutral"


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


# ---------------------------------------------------------------------- catalog
class Check(BaseModel):
    """A declarative best-practice rule — data, not UI (Constitution IV, FR-008)."""

    id: str
    label: str
    group: str
    tier: RemediationTier
    required_capabilities: dict[RemediationTier, list[Capability]] = Field(default_factory=dict)
    has_target: bool = False
    default_target: int | None = None
    evidence_fail: str = ""
    # Canonical reference explaining the rule (the tool/spec/docs it validates). Surfaced as a
    # deep-link on the catalog & policy page. None when the rule has no external reference (a
    # Hangar-specific concept). This is the single source of truth — the README mirrors it, and
    # a test (tests/unit/test_catalog_doc_urls.py) fails if the two drift.
    doc_url: str | None = None

    def tier_for(self, granted: set[Capability]) -> RemediationTier:
        """Resolve the effective tier for a connection's granted capabilities (FR-010).

        Write tiers degrade to deep-link, then report, when capabilities are missing.
        """
        order = [self.tier, RemediationTier.link, RemediationTier.report]
        for tier in order:
            needed = self.required_capabilities.get(tier, [])
            if all(cap in granted for cap in needed):
                return tier
        return RemediationTier.report


# --------------------------------------------------------------------- policy
class PolicyEntry(BaseModel):
    check_id: str
    enabled: bool = True
    params: dict[str, int | str | bool] = Field(default_factory=dict)
    severity: Severity = Severity.medium


class Policy(BaseModel):
    """Single editable fleet-wide policy at MVP (FR-019); multi-policy future-proofed (FR-020)."""

    id: str = "default"
    name: str = "Fleet baseline"
    entries: list[PolicyEntry] = Field(default_factory=list)

    def entry(self, check_id: str) -> PolicyEntry | None:
        return next((e for e in self.entries if e.check_id == check_id), None)

    def is_enabled(self, check_id: str) -> bool:
        e = self.entry(check_id)
        return e.enabled if e else False

    def target(self, check_id: str) -> int | None:
        e = self.entry(check_id)
        if e and "target" in e.params:
            return int(e.params["target"])
        return None


# ----------------------------------------------------------------- connections
class ProviderConnection(BaseModel):
    """A configured provider instance — the unit of attribution (FR-021–FR-026)."""

    id: str
    label: str
    provider_type: str  # "github" | "gitea"
    scope: str
    auth_mode: str
    granted_capabilities: set[Capability] = Field(default_factory=set)
    last_sync_at: datetime | None = None
    has_credential: bool = False  # True when a real provider credential is stored
    # The provider's browser-visible host for this connection — an OPAQUE string the core
    # never interprets. github.com by default; an enterprise connection overrides it
    # (e.g. https://ghe.example.com for GHES, https://acme.ghe.com for GHEC data residency).
    # The adapter (provider seam) derives the API host and UI URLs from it; the domain only
    # carries it, so multi-host support adds no platform branch to the core (Constitution I).
    base_url: str = "https://github.com"
    # The org/user that owns this connection's repos — a first-class, persisted field used
    # to build provider API paths. Defaults to the label suffix when not set explicitly, so
    # a label that doesn't follow the "prefix:owner" convention can still be addressed.
    owner: str = ""
    # GitHub App config (non-secret): the App id and the installation id this
    # connection authenticates as. None for PAT/token connections.
    app_id: str | None = None
    installation_id: int | None = None
    # Optional per-connection repo allowlist. ``None`` means "watch every repo the
    # credential can see" (the default); a list restricts the fleet to exactly those repo
    # names. Sync only interrogates allowlisted repos and prunes any that fall outside it,
    # so this both scopes the dashboard and bounds GitHub API/quota spend.
    repo_allowlist: list[str] | None = None
    # Decrypted secret material, attached in-memory only for live provider calls:
    # the App private-key PEM for App connections, or the access token for PAT/Gitea.
    # Excluded from serialization and repr so it never lands in a response or a log.
    token: str | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def _default_owner(self) -> ProviderConnection:
        if not self.owner:
            self.owner = self.label.split(":")[-1]
        return self

    @property
    def writes(self) -> bool:
        return (
            Capability.write_settings in self.granted_capabilities
            or Capability.open_pull_request in self.granted_capabilities
        )


# ----------------------------------------------------------------------- repo
class AlertCounts(BaseModel):
    critical: int = 0
    high: int = 0
    moderate: int = 0
    low: int = 0

    @property
    def total(self) -> int:
        return self.critical + self.high + self.moderate + self.low


class PullRequestSummary(BaseModel):
    """A real open pull request, captured by the poller into the cached snapshot so the
    repo-detail read can show actual PRs without a live provider call (Constitution VI)."""

    title: str = ""
    number: int | None = None
    url: str | None = None
    kind: str = "human"  # "dependabot" | "renovate" | "human" — the PR's real author
    created_at: str | None = None  # ISO timestamp; display age is derived at render
    draft: bool = False


class Repo(BaseModel):
    """A watched repository with a normalized snapshot (FR-001, FR-034)."""

    id: str
    connection_id: str
    description: str = ""
    default_branch: str = "main"
    open_prs: int = 0
    # Open PRs authored by a recognized dependency-update bot (Dependabot or Renovate).
    bot_prs: int = 0
    ci_status: CIStatus = CIStatus.none
    alerts: AlertCounts = Field(default_factory=AlertCounts)
    release_pending_days: int | None = None
    fails: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    # check_id -> reason, from the repo's committed .hangar.json. A suppressed check opts
    # out of scoring for this repo (neither pass nor fail); shown honestly as "suppressed",
    # never a fabricated pass (Constitution VIII). Empty when no config / unreadable.
    suppressions: dict[str, str] = Field(default_factory=dict)
    # SPDX id of the detected license (e.g. "MIT", "Apache-2.0") when the license check
    # passes; None when absent or unidentifiable (GitHub "NOASSERTION"). Used to enrich the
    # license finding's evidence ("MIT" rather than a generic "Detected").
    license_spdx: str | None = None
    # The most-recent open PRs (capped), captured by the poller for the activity strip.
    pull_requests: list[PullRequestSummary] = Field(default_factory=list)
    last_evaluated_at: datetime | None = None


# -------------------------------------------------------------------- findings
class Remediation(BaseModel):
    repo_id: str
    check_id: str
    kind: RemediationKind
    state: RemediationState
    pr_url: str | None = None
    pr_number: int | None = None
    idempotency_key: str | None = None


class Finding(BaseModel):
    repo_id: str
    check_id: str
    connection_id: str
    status: FindingStatus
    remediation_pending: bool = False
    evidence: str = ""
    open_pr_url: str | None = None


class AuditLogEntry(BaseModel):
    """Immutable record of one correction (FR-016) — append-only."""

    id: int | None = None
    timestamp: datetime
    connection_label: str  # denormalized: retained after connection removal
    actor: str             # always non-null (proxy identity or HANGAR_OPERATOR)
    repo_id: str
    check_label: str
    result: str
    pr_url: str | None = None
