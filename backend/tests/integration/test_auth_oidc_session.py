"""OIDC session enforcement: the signed session cookie gates /api/v1/* (Constitution III).

Mirrors the forward-auth header-trust suite. The session cookie is minted exactly the way
Starlette's SessionMiddleware signs it (itsdangerous TimestampSigner over base64-JSON), so we
can assert that a valid session admits, an expired one is rejected, and a forged one is too.
"""

from __future__ import annotations

import base64
import json
import time

import itsdangerous
import pytest
from fastapi.testclient import TestClient

from hangar.config import Settings, set_settings

_SESSION_SECRET = "test-session-signing-secret"
_COOKIE = "hangar_session"


@pytest.fixture
def oidc_app(monkeypatch):
    monkeypatch.setenv("HANGAR_ACCESS_MODE", "oidc")
    monkeypatch.setenv("HANGAR_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("HANGAR_OIDC_CLIENT_ID", "hangar")
    monkeypatch.setenv("HANGAR_OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setenv("HANGAR_SESSION_SECRET", _SESSION_SECRET)
    monkeypatch.setenv("HANGAR_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("HANGAR_HOST", "127.0.0.1")
    monkeypatch.delenv("HANGAR_FORWARD_AUTH", raising=False)
    set_settings(Settings())
    from hangar.main import create_app

    with TestClient(create_app()) as c:
        yield c


def _mint_session(payload: dict) -> str:
    """Forge a cookie value the way Starlette's SessionMiddleware would sign it."""
    signer = itsdangerous.TimestampSigner(_SESSION_SECRET)
    data = base64.b64encode(json.dumps(payload).encode())
    return signer.sign(data).decode()


def _with_session(payload: dict) -> dict[str, str]:
    return {"Cookie": f"{_COOKIE}={_mint_session(payload)}"}


def test_unauthenticated_api_is_401(oidc_app) -> None:
    assert oidc_app.get("/api/v1/me").status_code == 401


def test_auth_info_public_and_reports_unauthenticated(oidc_app) -> None:
    r = oidc_app.get("/auth/info")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "oidc"
    assert body["authenticated"] is False


def test_valid_session_admits_and_me_reflects_actor(oidc_app) -> None:
    headers = _with_session({"actor": "alice@example.com", "exp": int(time.time()) + 3600})
    r = oidc_app.get("/api/v1/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["actor"] == "alice@example.com"
    assert r.json()["access_mode"] == "oidc"


def test_expired_session_is_401(oidc_app) -> None:
    headers = _with_session({"actor": "alice@example.com", "exp": int(time.time()) - 1})
    assert oidc_app.get("/api/v1/me", headers=headers).status_code == 401


def test_forged_session_cookie_is_401(oidc_app) -> None:
    # Garbage that is not a valid signed value → SessionMiddleware yields an empty session.
    headers = {"Cookie": f"{_COOKIE}=not.a.valid.signed.cookie"}
    assert oidc_app.get("/api/v1/me", headers=headers).status_code == 401


def test_session_signed_with_wrong_secret_is_401(oidc_app) -> None:
    bad = itsdangerous.TimestampSigner("wrong-secret").sign(
        base64.b64encode(json.dumps({"actor": "mallory", "exp": int(time.time()) + 3600}).encode())
    ).decode()
    assert oidc_app.get("/api/v1/me", headers={"Cookie": f"{_COOKIE}={bad}"}).status_code == 401


@pytest.mark.parametrize("path", ["/health", "/auth/info"])
def test_public_paths_reachable_without_session(oidc_app, path) -> None:
    assert oidc_app.get(path).status_code == 200
