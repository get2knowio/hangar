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
from hangar.persistence.crypto import decrypt, encrypt
from hangar.persistence.models import ConnectionRow
from hangar.providers.registry import get_provider

log = structlog.get_logger(__name__)


def attach_credential(connection: ProviderConnection, row: ConnectionRow) -> ProviderConnection:
    """Decrypt and attach the stored credential for live provider calls (FR-032).

    No-op for credential-less (seeded/demo) connections. The token lives only in memory
    on ``connection.token`` (excluded from serialization/repr).
    """
    if row.credential_ciphertext:
        connection.token = decrypt(row.credential_ciphertext)
    return connection


async def list_connections(session: AsyncSession) -> list[ProviderConnection]:
    return await repo.list_connections(session)


def _slugify(label: str, provider_type: str) -> str:
    base = label.split(":")[0] if ":" in label else provider_type
    safe = "".join(ch if ch.isalnum() else "-" for ch in label.lower()).strip("-")
    return safe or f"{base}-conn"


# Capabilities every connection gets (read + deep-link); write tiers are opt-in.
_READ_CAPS = {
    Capability.read_settings,
    Capability.read_files,
    Capability.read_alerts,
    Capability.read_org_policy,
    Capability.deep_link,
    Capability.subscribe_webhooks,
}
_WRITE_CAPS = {Capability.write_settings, Capability.open_pull_request}


async def add_connection(
    session: AsyncSession,
    *,
    provider_type: str,
    label: str,
    scope: str,
    auth_mode: str = "",
    credential: str | None = None,
    writable: bool = False,
    app_id: str | None = None,
    installation_id: int | None = None,
    connection_id: str | None = None,
) -> ProviderConnection:
    """Add a connection. The credential is encrypted before it ever touches the DB.

    Granted capabilities are **least-privilege**: every connection gets read + deep-link
    (intersected with what the adapter can offer), and the write tiers
    (``write_settings``/``open_pull_request``) are granted ONLY when the operator
    declares the credential is writable (FR-026). We never assume a token can write just
    because the adapter *could* — a read-only PAT must register as read-only (FR-018).
    """
    # Fail closed: a writable connection MUST carry a credential. Without one, provider_for
    # would fall back to the demo simulator and fabricate a "PR opened" outcome + audit
    # entry for a write that never happened (Constitution III/VIII, FR-026). Refuse it.
    if writable and not credential:
        raise ValueError(
            "a writable connection requires a credential; refusing to grant write "
            "capabilities to a connection that cannot authenticate."
        )

    provider = get_provider(provider_type)
    offered = provider.declared_capabilities()
    granted = offered & _READ_CAPS
    if writable:
        granted |= offered & _WRITE_CAPS

    ciphertext = encrypt(credential) if credential else None
    cid = connection_id or _slugify(label, provider_type)

    row = ConnectionRow(
        id=cid,
        label=label,
        provider_type=provider_type,
        scope=scope,
        # The default auth-mode label is provided by the adapter (no platform branch here).
        auth_mode=auth_mode or provider.default_auth_mode,
        credential_ciphertext=ciphertext,
        granted_capabilities=[c.value for c in granted],
        app_id=app_id,
        installation_id=installation_id,
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
