"""Remediation orchestration (FR-010–FR-018; prototype ``fire``/``deep``/``markMerged``).

This is the human-triggered correction engine. It resolves the effective tier per the
connection's granted capabilities (FR-010), collapses write tiers to deep-link on
read-only connections (FR-018), enforces PR-first/idempotent behavior for content
corrections (FR-014/FR-015), drives the ``working → pr_open → fixed`` state machine
(FR-005a), and writes exactly one audit entry per correction (FR-016). It performs no
autonomous mutation — every call originates from an operator request (FR-017, AS-8).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from hangar.domain.checks import CATALOG
from hangar.domain.models import (
    Capability,
    ProviderConnection,
    RemediationKind,
    RemediationState,
    RemediationTier,
    Repo,
)
from hangar.persistence import repositories as repo_store
from hangar.providers.base import CorrectionRequest, RepoProvider, provider_name
from hangar.services import audit


class ReadOnlyCollapse(Exception):
    """Raised when a write correction is requested on a connection lacking write scope.

    Carries the deep-link the caller should surface instead (FR-018 → API 403).
    """

    def __init__(self, deep_link_url: str) -> None:
        super().__init__("connection lacks write scope; collapsed to deep-link")
        self.deep_link_url = deep_link_url


class NoOpenPullRequest(Exception):
    """Raised when ``mark_merged`` is called for a check with no open Hangar PR.

    Prevents fabricating a 'PR merged' pass + audit entry for a PR that never existed
    (FR-016 audit integrity → API 409).
    """

    def __init__(self, check_id: str) -> None:
        super().__init__(f"no open Hangar PR to mark merged for check '{check_id}'")
        self.check_id = check_id


@dataclass(slots=True)
class RemediationOutcome:
    state: RemediationState
    pr_url: str | None
    idempotent_hit: bool
    audit_id: int | None
    result_text: str


def resolve_kind(check_id: str, connection: ProviderConnection) -> RemediationKind:
    """Map a check's effective tier (given the connection) to a remediation kind."""
    check = CATALOG[check_id]
    tier = check.tier_for(connection.granted_capabilities)
    return {
        RemediationTier.patch: RemediationKind.settings_patch,
        RemediationTier.pr: RemediationKind.config_pr,
        RemediationTier.link: RemediationKind.deep_link,
        RemediationTier.report: RemediationKind.report,
    }[tier]


class RemediationService:
    def __init__(self, provider: RepoProvider) -> None:
        self.provider = provider

    async def remediate(
        self,
        session: AsyncSession,
        *,
        connection: ProviderConnection,
        repo: Repo,
        check_id: str,
        kind: RemediationKind,
        actor: str,
    ) -> RemediationOutcome:
        check = CATALOG[check_id]
        writable = connection.writes
        is_write_kind = kind in (RemediationKind.settings_patch, RemediationKind.config_pr)

        # Read-only collapse (FR-018): a write request on a read-only connection becomes
        # a deep-link; never silently a no-op.
        if is_write_kind and not writable:
            deep = self.provider.deep_link(connection, repo, check_id)
            await audit.record_correction(
                session, actor=actor, connection_label=connection.label,
                repo_id=repo.id, check_label=check.label,
                result=f"Opened in {provider_name(connection.provider_type)}",
            )
            raise ReadOnlyCollapse(deep)

        # Idempotency for PR corrections (FR-015): surface an existing open Hangar PR.
        if kind is RemediationKind.config_pr:
            existing = await repo_store.get_remediation(session, connection.id, repo.id, check_id)
            if existing is not None and existing.state == RemediationState.pr_open.value:
                return RemediationOutcome(
                    state=RemediationState.pr_open, pr_url=existing.pr_url,
                    idempotent_hit=True, audit_id=None,
                    result_text=f"PR #{existing.pr_number} already open",
                )

        # Apply via the provider. Settings converge; content opens a PR (never a push).
        request = CorrectionRequest(
            repo=repo, check_id=check_id, check_label=check.label, kind=kind
        )
        result = await self.provider.correct(connection, request)

        if kind is RemediationKind.deep_link:
            entry = await audit.record_correction(
                session, actor=actor, connection_label=connection.label,
                repo_id=repo.id, check_label=check.label,
                result=f"Opened in {provider_name(connection.provider_type)}",
                pr_url=result.deep_link_url,
            )
            return RemediationOutcome(
                state=RemediationState.deep_link, pr_url=result.deep_link_url,
                idempotent_hit=False, audit_id=entry.id, result_text="Opened in provider",
            )

        if kind is RemediationKind.report:
            entry = await audit.record_correction(
                session, actor=actor, connection_label=connection.label,
                repo_id=repo.id, check_label=check.label, result="Reported",
            )
            return RemediationOutcome(
                state=RemediationState.fixed, pr_url=None, idempotent_hit=False,
                audit_id=entry.id, result_text="Reported",
            )

        if kind is RemediationKind.config_pr:
            pr_number = result.pr_number
            if pr_number is None and not result.idempotent_hit:
                pr_number = await repo_store.next_pr_number(session)
            # URL construction is the provider's job (provider-agnostic core, Constitution I).
            pr_url = result.pr_url or self.provider.pr_url(connection, repo, pr_number)
            await repo_store.upsert_remediation(
                session, connection_id=connection.id, repo_id=repo.id, check_id=check_id,
                kind=kind.value, state=RemediationState.pr_open.value,
                pr_url=pr_url, pr_number=pr_number,
                idempotency_key=f"{connection.id}::{repo.id}::{check_id}",
            )
            if result.idempotent_hit:
                return RemediationOutcome(
                    state=RemediationState.pr_open, pr_url=pr_url, idempotent_hit=True,
                    audit_id=None, result_text=f"PR #{pr_number} already open",
                )
            entry = await audit.record_correction(
                session, actor=actor, connection_label=connection.label,
                repo_id=repo.id, check_label=check.label,
                result=f"PR #{pr_number} opened", pr_url=pr_url,
            )
            return RemediationOutcome(
                state=RemediationState.pr_open, pr_url=pr_url, idempotent_hit=False,
                audit_id=entry.id, result_text=f"PR #{pr_number} opened",
            )

        # settings_patch
        await repo_store.upsert_remediation(
            session, connection_id=connection.id, repo_id=repo.id, check_id=check_id,
            kind=kind.value, state=RemediationState.fixed.value,
        )
        entry = await audit.record_correction(
            session, actor=actor, connection_label=connection.label,
            repo_id=repo.id, check_label=check.label, result="Settings applied",
        )
        return RemediationOutcome(
            state=RemediationState.fixed, pr_url=None, idempotent_hit=False,
            audit_id=entry.id, result_text="Settings applied",
        )

    async def mark_merged(
        self,
        session: AsyncSession,
        *,
        connection: ProviderConnection,
        repo: Repo,
        check_id: str,
        actor: str,
    ) -> RemediationOutcome:
        check = CATALOG[check_id]
        # Only a check with an open Hangar PR can be "merged" — otherwise this would
        # fabricate a pass + 'PR merged' audit entry for a PR that never existed (FR-016).
        existing = await repo_store.get_remediation(session, connection.id, repo.id, check_id)
        if existing is None or existing.state != RemediationState.pr_open.value:
            raise NoOpenPullRequest(check_id)
        await repo_store.upsert_remediation(
            session, connection_id=connection.id, repo_id=repo.id, check_id=check_id,
            kind=RemediationKind.config_pr.value, state=RemediationState.fixed.value,
            pr_url=existing.pr_url, pr_number=existing.pr_number,
        )
        entry = await audit.record_correction(
            session, actor=actor, connection_label=connection.label,
            repo_id=repo.id, check_label=check.label, result="PR merged", pr_url=existing.pr_url,
        )
        return RemediationOutcome(
            state=RemediationState.fixed, pr_url=existing.pr_url, idempotent_hit=False,
            audit_id=entry.id, result_text="PR merged",
        )


# Capability re-export so callers don't reach into models for the common check.
__all__ = [
    "RemediationService", "RemediationOutcome", "ReadOnlyCollapse", "NoOpenPullRequest",
    "resolve_kind", "Capability",
]
