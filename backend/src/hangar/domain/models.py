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

from pydantic import BaseModel, Field


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


class RemediationKind(StrEnum):
    report = "report"
    deep_link = "deep_link"
    settings_patch = "settings_patch"
    config_pr = "config_pr"


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
    # Decrypted credential, attached in-memory only for live provider calls. Excluded
    # from serialization and repr so it never lands in an API response or a log line.
    token: str | None = Field(default=None, exclude=True, repr=False)

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


class Repo(BaseModel):
    """A watched repository with a normalized snapshot (FR-001, FR-034)."""

    id: str
    connection_id: str
    description: str = ""
    default_branch: str = "main"
    open_prs: int = 0
    dependabot_prs: int = 0
    ci_status: CIStatus = CIStatus.none
    alerts: AlertCounts = Field(default_factory=AlertCounts)
    release_pending_days: int | None = None
    fails: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
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
