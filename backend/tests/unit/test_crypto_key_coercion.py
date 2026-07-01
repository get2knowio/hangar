"""HANGAR_SECRET_KEY coercion — accept any high-entropy secret, not only Fernet keys.

Fernet requires a 32-byte url-safe-base64 key (``Fernet.generate_key()``, 44 chars).
Operators and Hola's install-wizard "generate" button commonly supply a raw secret in
another encoding (e.g. ``openssl rand -hex 32`` → 64 hex chars). Those are rejected by
raw ``Fernet(key)`` and used to 500 the GitHub App creation callback when it tried to
encrypt the App private key. ``_coerce_fernet_key`` folds such secrets into a valid key.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from hangar.config import Settings, set_settings
from hangar.persistence.crypto import _coerce_fernet_key, decrypt, encrypt

# 32 random bytes as hex — the shape `openssl rand -hex 32` / Hola's 🪄 button emits.
HEX_KEY = "a" * 64


def test_valid_fernet_key_passes_through_verbatim() -> None:
    key = Fernet.generate_key().decode()
    # A real Fernet key must be used as-is so existing installs keep decrypting old data.
    assert _coerce_fernet_key(key) == key.encode()


def test_hex_secret_is_coerced_to_a_usable_key() -> None:
    coerced = _coerce_fernet_key(HEX_KEY)
    # The result is a real, constructible Fernet key (44 url-safe-base64 chars).
    Fernet(coerced)  # does not raise


def test_coercion_is_deterministic() -> None:
    # Same secret → same key, so nothing needs migrating across restarts.
    assert _coerce_fernet_key(HEX_KEY) == _coerce_fernet_key(HEX_KEY)
    assert _coerce_fernet_key(HEX_KEY) != _coerce_fernet_key("b" * 64)


def test_bytes_and_str_secret_agree() -> None:
    assert _coerce_fernet_key(HEX_KEY) == _coerce_fernet_key(HEX_KEY.encode())


def test_encrypt_decrypt_round_trips_with_hex_secret() -> None:
    # The end-to-end path that used to 500 in app_created(): a hex secret now works.
    set_settings(Settings(secret_key=HEX_KEY))
    try:
        plaintext = "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"
        assert decrypt(encrypt(plaintext)) == plaintext
    finally:
        set_settings(Settings())
