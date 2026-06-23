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
    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    granted_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    app_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    installation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_domain(self) -> ProviderConnection:
        return ProviderConnection(
            id=self.id,
            label=self.label,
            provider_type=self.provider_type,
            scope=self.scope,
            auth_mode=self.auth_mode,
            granted_capabilities={Capability(c) for c in (self.granted_capabilities or [])},
            app_id=self.app_id,
            installation_id=self.installation_id,
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
