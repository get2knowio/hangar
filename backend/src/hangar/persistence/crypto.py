"""Credential encryption at rest — Fernet (FR-032, research.md §5).

Provider secrets (GitHub App private key, webhook secrets, Gitea tokens) are stored
as Fernet ciphertext keyed on ``HANGAR_SECRET_KEY``. There is no bespoke crypto
(Constitution III). Hangar refuses to persist a writable credential if the key is
absent.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from hangar.config import get_settings


class CredentialEncryptionError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().secret_key
    if not key:
        raise CredentialEncryptionError(
            "HANGAR_SECRET_KEY is not set — cannot encrypt/decrypt provider credentials "
            "(FR-032). Generate one with: python -c "
            "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
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
