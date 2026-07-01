"""Credential encryption at rest — Fernet (FR-032, research.md §5).

Provider secrets (GitHub App private key, webhook secrets, Gitea tokens) are stored
as Fernet ciphertext keyed on ``HANGAR_SECRET_KEY``. There is no bespoke crypto
(Constitution III). Hangar refuses to persist a writable credential if the key is
absent.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from hangar.config import get_settings


class CredentialEncryptionError(RuntimeError):
    pass


def _coerce_fernet_key(key: str | bytes) -> bytes:
    """Turn any operator-supplied secret into a valid Fernet key.

    A Fernet key must be exactly 32 url-safe-base64-encoded bytes (a 44-char key,
    i.e. ``Fernet.generate_key()``). Operators — and Hola's install wizard "generate"
    button — commonly supply a raw high-entropy secret in another encoding instead,
    e.g. ``openssl rand -hex 32`` (64 hex chars). Those have plenty of entropy but the
    wrong shape, so ``Fernet(key)`` rejects them and credential encryption 500s.

    A proper Fernet key is used verbatim (existing installs keep their exact key, so
    already-encrypted data still decrypts). Anything else is deterministically folded
    into a valid key via SHA-256 — same input always yields the same key, so nothing
    needs migrating.
    """
    raw = key.encode() if isinstance(key, str) else key
    try:
        # Accept an already-valid Fernet key as-is (no re-derivation, no migration).
        Fernet(raw)
        return raw
    except (ValueError, TypeError):
        digest = hashlib.sha256(raw).digest()  # 32 bytes
        return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    key = get_settings().secret_key
    if not key:
        raise CredentialEncryptionError(
            "HANGAR_SECRET_KEY is not set — cannot encrypt/decrypt provider credentials "
            "(FR-032). Generate one with: python -c "
            "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    try:
        return Fernet(_coerce_fernet_key(key))
    except (ValueError, TypeError) as exc:
        raise CredentialEncryptionError(f"HANGAR_SECRET_KEY is not a valid Fernet key: {exc}") from exc


def encrypt(plaintext: str) -> bytes:
    """Encrypt a secret for storage. Returns ciphertext bytes."""
    return _fernet().encrypt(plaintext.encode())


def decrypt(ciphertext: bytes) -> str:
    """Decrypt a stored secret. Raises on tamper/wrong key."""
    try:
        return _fernet().decrypt(ciphertext).decode()
    except InvalidToken as exc:
        raise CredentialEncryptionError("credential ciphertext failed to decrypt") from exc


def generate_key() -> str:
    """Generate a fresh Fernet key (used by setup docs/tests)."""
    return Fernet.generate_key().decode()
