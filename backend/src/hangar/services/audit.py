"""Append-only audit log service (FR-016, SC-008) + actor resolution (FR-016, T072).

Every correction writes exactly one immutable entry with an **always non-null** actor:
the forward-auth proxy identity when enforced, else ``HANGAR_OPERATOR`` (default
``local-operator``) in disabled mode. Connection attribution is denormalized onto the
entry so the trail survives connection removal (clarification).
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.config import AccessMode, Settings, get_settings
from hangar.domain.models import AuditLogEntry
from hangar.persistence import repositories as repo

log = structlog.get_logger(__name__)


def resolve_actor(settings: Settings | None = None, proxy_identity: str | None = None) -> str:
    """Audit actor for the current request — never null (FR-016, clarification)."""
    settings = settings or get_settings()
    if settings.access_mode is AccessMode.forward_auth and proxy_identity:
        return proxy_identity
    if settings.access_mode is AccessMode.forward_auth:
        # Enforced mode but no identity surfaced — should not happen past middleware.
        return settings.forward_auth_allowed_user or "unknown"
    return settings.operator


async def record_correction(
    session: AsyncSession,
    *,
    actor: str,
    connection_label: str,
    repo_id: str,
    check_label: str,
    result: str,
    pr_url: str | None = None,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        timestamp=datetime.now(UTC),
        connection_label=connection_label,
        actor=actor,
        repo_id=repo_id,
        check_label=check_label,
        result=result,
        pr_url=pr_url,
    )
    saved = await repo.append_audit(session, entry)
    log.info(
        "audit.correction",
        actor=actor, connection=connection_label, repo=repo_id,
        check=check_label, result=result, pr_url=pr_url,
    )
    return saved
