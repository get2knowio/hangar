"""Webhook reconciliation (FR-033, Constitution VI).

Provider-specific verification + parsing live behind the RepoProvider seam
(``verify_webhook`` / ``parse_webhook``); this service only applies the normalized
:class:`~hangar.providers.base.WebhookEvent` to the cached snapshot. Reads continue to
serve the cache, so a missed webhook simply means the next poll reconciles (resilience).
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.persistence.models import RepoRow
from hangar.providers.base import WebhookEvent

log = structlog.get_logger(__name__)


async def apply_event(session: AsyncSession, event: WebhookEvent, connection_id: str) -> bool:
    """Apply a verified, normalized event to the snapshot. Returns True if a repo updated.

    The repo is resolved by ``(name, connection_id)`` — the connection comes from the
    webhook URL — so a same-named repo on another connection is never touched.
    """
    row = await session.get(RepoRow, (event.repo_name, connection_id))
    if row is None:
        return False

    changed = False
    if event.ci_status is not None:
        row.ci_status = event.ci_status
        changed = True
    if event.pr_delta:
        row.open_prs = max(0, row.open_prs + event.pr_delta)
        # Keep the Dependabot sub-count consistent with open_prs (a closed bot PR must
        # decrement both, else dependabot_prs can exceed open_prs until the next poll).
        if event.pr_is_bot:
            row.dependabot_prs = max(0, row.dependabot_prs + event.pr_delta)
        row.dependabot_prs = min(row.dependabot_prs, row.open_prs)
        changed = True

    if changed:
        await session.commit()
        log.info("webhook.applied", repo=event.repo_name, connection=connection_id)
    return changed
