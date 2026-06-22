"""Webhook receiver (FR-033, Constitution VI).

Near-real-time provider events update the cached snapshot between polls. Signatures are
verified with the per-connection webhook secret before any state change; an unverified
payload is rejected. Reads continue to serve the cache, so a missed webhook simply means
the next poll reconciles (resilience).
"""

from __future__ import annotations

import hashlib
import hmac

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.persistence.models import RepoRow

log = structlog.get_logger(__name__)


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Verify a GitHub ``X-Hub-Signature-256`` HMAC (sha256=...)."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


async def apply_event(
    session: AsyncSession, event: str, payload: dict, connection_id: str
) -> bool:
    """Reconcile a verified event into the snapshot. Returns True if a repo updated.

    The repo is resolved by ``(name, connection_id)`` — the connection comes from the
    webhook URL — so a same-named repo on another connection is never touched.
    """
    repo_name = (payload.get("repository") or {}).get("name")
    if not repo_name:
        return False
    row = await session.get(RepoRow, (repo_name, connection_id))
    if row is None:
        return False

    if event == "check_suite" or event == "workflow_run":
        conclusion = (payload.get(event) or {}).get("conclusion")
        if conclusion in {"success", "failure"}:
            row.ci_status = "pass" if conclusion == "success" else "fail"
    elif event == "pull_request":
        action = payload.get("action")
        if action in {"opened", "reopened", "closed"}:
            delta = 1 if action in {"opened", "reopened"} else -1
            row.open_prs = max(0, row.open_prs + delta)
            # Keep the Dependabot sub-count consistent with open_prs (a closed bot PR must
            # decrement both, else dependabot_prs can exceed open_prs and corrupt the
            # derived human-PR count until the next poll reconciles).
            login = ((payload.get("pull_request") or {}).get("user") or {}).get("login")
            if login in {"dependabot[bot]", "dependabot-preview[bot]"}:
                row.dependabot_prs = max(0, row.dependabot_prs + delta)
            row.dependabot_prs = min(row.dependabot_prs, row.open_prs)
    elif event in {"repository_vulnerability_alert", "dependabot_alert"}:
        # Re-derive on next poll; mark for freshness here.
        pass
    else:
        return False

    await session.commit()
    # NB: structlog reserves the ``event`` kwarg for the message, so the GitHub event
    # name is logged as ``gh_event`` to avoid a TypeError collision.
    log.info("webhook.applied", gh_event=event, repo=repo_name)
    return True
