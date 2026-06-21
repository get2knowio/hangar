"""Webhook HMAC signature verification (FR-033)."""

from __future__ import annotations

import hashlib
import hmac

from hangar.services.webhooks import verify_signature

_SECRET = "webhook-secret"
_BODY = b'{"action":"opened"}'


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_accepts_correct_signature() -> None:
    sig = _sign(_SECRET, _BODY)
    assert verify_signature(_SECRET, _BODY, sig) is True


def test_rejects_forged_signature() -> None:
    forged = "sha256=" + "0" * 64
    assert verify_signature(_SECRET, _BODY, forged) is False


def test_rejects_wrong_secret() -> None:
    sig = _sign("other-secret", _BODY)
    assert verify_signature(_SECRET, _BODY, sig) is False


def test_rejects_missing_signature() -> None:
    assert verify_signature(_SECRET, _BODY, None) is False
    assert verify_signature(_SECRET, _BODY, "") is False


def test_rejects_unprefixed_signature() -> None:
    raw = hmac.new(_SECRET.encode(), _BODY, hashlib.sha256).hexdigest()
    assert verify_signature(_SECRET, _BODY, raw) is False
