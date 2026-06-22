"""T069 — provider credentials are encrypted at rest (FR-032)."""

from __future__ import annotations

from sqlalchemy import select

from hangar.persistence.crypto import decrypt
from hangar.persistence.db import create_all, get_sessionmaker
from hangar.persistence.models import ConnectionRow
from hangar.services import connections as conn_service


async def test_credential_stored_encrypted_and_round_trips() -> None:
    await create_all()
    plaintext = "super-secret-token-xyz"
    sm = get_sessionmaker()
    async with sm() as session:
        conn = await conn_service.add_connection(
            session,
            provider_type="github",
            label="gh:crypto-test",
            scope="org · 1 repos",
            auth_mode="GitHub App",
            credential=plaintext,
        )
        assert conn.has_credential is True

    async with sm() as session:
        row = (
            await session.execute(
                select(ConnectionRow).where(ConnectionRow.label == "gh:crypto-test")
            )
        ).scalar_one()
        ct = row.credential_ciphertext
        assert ct is not None
        assert isinstance(ct, (bytes, bytearray))
        # ciphertext is NOT the plaintext
        assert plaintext.encode() not in bytes(ct)
        assert bytes(ct) != plaintext.encode()
        # decrypts back to the original plaintext
        assert decrypt(bytes(ct)) == plaintext


async def test_no_credential_leaves_ciphertext_null() -> None:
    await create_all()
    sm = get_sessionmaker()
    async with sm() as session:
        await conn_service.add_connection(
            session,
            provider_type="gitea",
            label="gitea:no-cred",
            scope="user · 1 repos",
            credential=None,
        )
    async with sm() as session:
        row = (
            await session.execute(
                select(ConnectionRow).where(ConnectionRow.label == "gitea:no-cred")
            )
        ).scalar_one()
        assert row.credential_ciphertext is None
