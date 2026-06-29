"""SQLAlchemy ORM models (SQLite/Postgres) and domain conversion.

Findings are *derived* (repo snapshot × active policy × remediation overlay), so they
are not stored. We persist connections, repo snapshots, in-flight remediations, the
single policy, and the append-only audit log. The same logical repo name under two
connections is two distinct rows keyed on the composite ``(id, connection_id)`` PK, and
every access path resolves by that pair — never by name alone (Constitution I).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from hangar.domain.models import (
    AlertCounts,
    Capability,
    CIStatus,
    ProviderConnection,
    PullRequestSummary,
    Repo,
)
from hangar.persistence.db import Base


class ConnectionRow(Base):
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128))
    provider_type: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(128))
    auth_mode: Mapped[str] = mapped_column(String(128))
    # Org/user that owns the repos (first-class; defaults to the label suffix at creation).
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Provider browser host for this connection (github.com by default; an enterprise host
    # for GHES/GHEC). Opaque to the core — the adapter derives API/UI URLs from it.
    base_url: Mapped[str] = mapped_column(
        String(255), nullable=False, default="https://github.com",
        server_default="https://github.com",
    )
    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Per-connection webhook HMAC secret (encrypted at rest). When null, the inbound
    # webhook falls back to the global HANGAR_WEBHOOK_SECRET.
    webhook_secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    granted_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    app_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    installation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Optional repo allowlist (JSON list of repo names). NULL = watch all repos the
    # credential can see; a list scopes the connection to exactly those repos.
    repo_allowlist: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_domain(self) -> ProviderConnection:
        return ProviderConnection(
            id=self.id,
            label=self.label,
            provider_type=self.provider_type,
            scope=self.scope,
            auth_mode=self.auth_mode,
            owner=self.owner or "",  # empty → ProviderConnection derives it from the label
            base_url=self.base_url or "https://github.com",
            granted_capabilities={Capability(c) for c in (self.granted_capabilities or [])},
            app_id=self.app_id,
            installation_id=self.installation_id,
            repo_allowlist=list(self.repo_allowlist) if self.repo_allowlist is not None else None,
            last_sync_at=self.last_sync_at,
            has_credential=self.credential_ciphertext is not None,
        )


class RepoRow(Base):
    __tablename__ = "repos"

    # Composite key: the SAME repo name under two connections is two distinct rows,
    # each attributed and evaluated independently (data-model.md; FR-023). Keying on
    # name alone would let one connection's sync silently overwrite another's snapshot.
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), primary_key=True
    )
    description: Mapped[str] = mapped_column(Text, default="")
    default_branch: Mapped[str] = mapped_column(String(64), default="main")
    open_prs: Mapped[int] = mapped_column(Integer, default=0)
    dependabot_prs: Mapped[int] = mapped_column(Integer, default=0)
    ci_status: Mapped[str] = mapped_column(String(8), default="none")
    alerts: Mapped[dict] = mapped_column(JSON, default=dict)
    release_pending_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fails: Mapped[list[str]] = mapped_column(JSON, default=list)
    unknowns: Mapped[list[str]] = mapped_column(JSON, default=list)
    # SPDX id of the detected license (e.g. "MIT"); NULL when absent/unidentifiable.
    license_spdx: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Captured open PRs (title/number/url/kind/created_at/draft) for the activity strip.
    pull_requests: Mapped[list | None] = mapped_column(JSON, nullable=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_domain(self) -> Repo:
        a = self.alerts or {}
        return Repo(
            id=self.id,
            connection_id=self.connection_id,
            description=self.description,
            default_branch=self.default_branch,
            open_prs=self.open_prs,
            dependabot_prs=self.dependabot_prs,
            ci_status=CIStatus(self.ci_status),
            alerts=AlertCounts(
                critical=a.get("critical", a.get("c", 0)),
                high=a.get("high", a.get("h", 0)),
                moderate=a.get("moderate", a.get("m", 0)),
                low=a.get("low", a.get("l", 0)),
            ),
            release_pending_days=self.release_pending_days,
            fails=list(self.fails or []),
            unknowns=list(self.unknowns or []),
            license_spdx=self.license_spdx,
            pull_requests=[PullRequestSummary(**p) for p in (self.pull_requests or [])],
            last_evaluated_at=self.last_evaluated_at,
        )


class RemediationRow(Base):
    __tablename__ = "remediations"

    # Connection-scoped: the same repo name under two connections has independent
    # remediation state, mirroring RepoRow's composite key. Keying on repo_id alone would
    # let a fix opened on one connection's repo overlay another connection's same-named repo.
    connection_id: Mapped[str] = mapped_column(String(64), primary_key=True, default="")
    repo_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    check_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(16))
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    connection_label: Mapped[str] = mapped_column(String(128))
    actor: Mapped[str] = mapped_column(String(128))
    repo_id: Mapped[str] = mapped_column(String(128))
    check_label: Mapped[str] = mapped_column(String(128))
    result: Mapped[str] = mapped_column(String(256))
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class PolicyRow(Base):
    __tablename__ = "policy"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default="default")
    name: Mapped[str] = mapped_column(String(128), default="Fleet baseline")
    entries: Mapped[list] = mapped_column(JSON, default=list)


class GitHubAppRegistration(Base):
    """A GitHub App provisioned via the manifest flow — **one per browser host**.

    Keyed on ``base_url`` so a single Hangar can hold a distinct App for github.com, a GHEC
    data-residency tenant, and a GHES instance. Each installation-connection references it by
    host + ``app_id`` and stores only its own ``installation_id``; this lets a later "Connect"
    on another org reuse the same App instead of creating a new one. All secret material (the
    private-key PEM, webhook + client secrets) is Fernet-encrypted at rest (FR-032).
    """

    __tablename__ = "github_app_registrations"

    base_url: Mapped[str] = mapped_column(String(255), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(32))
    slug: Mapped[str] = mapped_column(String(128))
    client_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    private_key_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    webhook_secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    client_secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
