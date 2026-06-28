"""End-to-end OIDC Authorization-Code + PKCE flow against a mocked IdP.

respx intercepts the app's *outbound* Authlib calls to the IdP (discovery, JWKS, token); the
TestClient→app calls go through ASGITransport and are untouched. The IdP signs a real RS256
ID token with a generated key, embedding the nonce Authlib put in the authorize request — so
this exercises genuine PKCE, state(CSRF), nonce(replay), and signature validation.
"""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from authlib.jose import JsonWebKey, jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from hangar.auth.oidc import is_admitted, reset_oauth
from hangar.config import Settings, set_settings

ISSUER = "https://idp.example.com"
CLIENT_ID = "hangar"
SESSION_SECRET = "flow-session-secret"
KID = "test-key"


@pytest.fixture
def keypair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def oidc_app(monkeypatch):
    monkeypatch.setenv("HANGAR_ACCESS_MODE", "oidc")
    monkeypatch.setenv("HANGAR_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("HANGAR_OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("HANGAR_OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setenv("HANGAR_SESSION_SECRET", SESSION_SECRET)
    monkeypatch.setenv("HANGAR_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("HANGAR_OIDC_REDIRECT_URL", "http://testserver/auth/callback")
    monkeypatch.setenv("HANGAR_HOST", "127.0.0.1")
    monkeypatch.delenv("HANGAR_FORWARD_AUTH", raising=False)
    set_settings(Settings())
    reset_oauth()  # rebuild Authlib registry from these settings
    from hangar.main import create_app

    with TestClient(create_app()) as c:
        yield c
    reset_oauth()


def _metadata() -> dict:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/jwks",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }


def _jwks(key: rsa.RSAPrivateKey) -> dict:
    jwk = JsonWebKey.import_key(key.public_key(), {"kty": "RSA", "use": "sig", "kid": KID})
    return {"keys": [jwk.as_dict()]}


def _id_token(key: rsa.RSAPrivateKey, nonce: str, claims: dict | None = None) -> str:
    now = int(time.time())
    payload = {
        "iss": ISSUER, "aud": CLIENT_ID, "sub": "user-123",
        "email": "alice@example.com", "iat": now, "exp": now + 3600, "nonce": nonce,
    }
    if claims:
        payload.update(claims)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return jwt.encode({"alg": "RS256", "kid": KID}, payload, pem).decode()


def _drive_login(client: TestClient, router: respx.MockRouter) -> tuple[str, str]:
    """GET /auth/login; assert PKCE + return (state, nonce) from the authorize redirect."""
    router.get(f"{ISSUER}/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=_metadata())
    )
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    assert urlparse(loc).netloc == "idp.example.com"
    q = parse_qs(urlparse(loc).query)
    assert q["code_challenge_method"] == ["S256"]  # PKCE
    assert q["redirect_uri"] == ["http://testserver/auth/callback"]
    return q["state"][0], q["nonce"][0]


def test_full_oidc_login_flow_admits_and_sets_session(oidc_app, keypair) -> None:
    with respx.mock(assert_all_called=False) as router:
        state, nonce = _drive_login(oidc_app, keypair_router(router, keypair))
        router.post(f"{ISSUER}/token").mock(
            return_value=httpx.Response(200, json={
                "access_token": "at", "token_type": "Bearer",
                "id_token": _id_token(keypair, nonce), "expires_in": 3600,
            })
        )
        r = oidc_app.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"

    # The session cookie now admits API calls and reflects the resolved identity.
    me = oidc_app.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["actor"] == "alice@example.com"
    assert me.json()["access_mode"] == "oidc"


def test_callback_with_bad_state_is_rejected(oidc_app, keypair) -> None:
    with respx.mock(assert_all_called=False) as router:
        _drive_login(oidc_app, keypair_router(router, keypair))
        # A mismatched state (CSRF) must fail before any token exchange.
        r = oidc_app.get("/auth/callback?code=abc&state=forged", follow_redirects=False)
        assert r.status_code == 401
    assert oidc_app.get("/api/v1/me").status_code == 401  # still no session


def keypair_router(router: respx.MockRouter, key: rsa.RSAPrivateKey) -> respx.MockRouter:
    """Register the JWKS endpoint and return the router (for chaining in _drive_login)."""
    router.get(f"{ISSUER}/jwks").mock(return_value=httpx.Response(200, json=_jwks(key)))
    return router


# --- allowlist (is_admitted) — unit-level, no IdP needed ---


def _claims(email="alice@example.com", sub="user-123", groups=None):
    c = {"email": email, "sub": sub}
    if groups is not None:
        c["groups"] = groups
    return c


def test_is_admitted_empty_allowlist_admits_all() -> None:
    s = Settings(access_mode_select="oidc")
    assert is_admitted(_claims(), s) is True


def test_is_admitted_user_allowlist() -> None:
    s = Settings(access_mode_select="oidc", oidc_allowed_users="alice@example.com")
    assert is_admitted(_claims(email="alice@example.com"), s) is True
    assert is_admitted(_claims(email="bob@example.com"), s) is False


def test_is_admitted_group_allowlist() -> None:
    s = Settings(access_mode_select="oidc", oidc_allowed_groups="admins")
    assert is_admitted(_claims(groups=["admins", "users"]), s) is True
    assert is_admitted(_claims(groups=["users"]), s) is False
