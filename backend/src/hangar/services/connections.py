"""Connection management (FR-021–FR-026, FR-032).

Multiple connections — including several of the same provider type — are configuration,
not code (FR-022/FR-024). Credentials are encrypted at rest via Fernet (FR-032), and a
connection captures only the least-privilege capability subset its scopes grant
(FR-026). Removing a connection drops its repos/findings/snapshots but **retains its
audit entries** with denormalized attribution (clarification).
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.domain.models import Capability, ProviderConnection
from hangar.persistence import repositories as repo
from hangar.persistence.crypto import encrypt
from hangar.persistence.models import ConnectionRow
from hangar.providers.registry import get_provider

log = structlog.get_logger(__name__)


async def list_connections(session: AsyncSession) -> list[ProviderConnection]:
    return await repo.list_connections(session)


def _slugify(label: str, provider_type: str) -> str:
    base = label.split(":")[0] if ":" in label else provider_type
    safe = "".join(ch if ch.isalnum() else "-" for ch in label.lower()).strip("-")
    return safe or f"{base}-conn"


async def add_connection(
    session: AsyncSession,
    *,
    provider_type: str,
    label: str,
    scope: str,
    auth_mode: str = "",
    credential: str | None = None,
    connection_id: str | None = None,
) -> ProviderConnection:
    """Add a connection. The credential is encrypted before it ever touches the DB.

    Granted capabilities are the intersection of what the adapter can offer and what a
    connection of this type is permitted at MVP (Gitea = read + deep-link only).
    """
    provider = get_provider(provider_type)
    granted = provider.declared_capabilities()

    ciphertext = encrypt(credential) if credential else None
    cid = connection_id or _slugify(label, provider_type)

    row = ConnectionRow(
        id=cid,
        label=label,
        provider_type=provider_type,
        scope=scope,
        auth_mode=auth_mode or ("GitHub App" if provider_type == "github" else "Scoped token"),
        credential_ciphertext=ciphertext,
        granted_capabilities=[c.value for c in granted],
        last_sync_at=None,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
    log.info("connection.added", id=cid, provider=provider_type, writes=_writes(granted))
    return row.to_domain()


async def remove_connection(session: AsyncSession, connection_id: str) -> None:
    """Drop the connection + repos/snapshots; audit entries are retained (clarification)."""
    await repo.delete_connection(session, connection_id)
    log.info("connection.removed", id=connection_id, audit_retained=True)


def _writes(granted: set[Capability]) -> bool:
    return Capability.write_settings in granted or Capability.open_pull_request in granted
