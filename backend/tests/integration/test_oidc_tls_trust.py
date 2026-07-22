"""OIDC IdP TLS trust configuration (issue #34).

Hangar can trust an internal-CA/self-signed IdP for the discovery/JWKS/token calls, and
surfaces an unreachable/untrusted IdP as a clear 502 instead of a bare 500 — while leaving
the default (public-CA, e.g. Let's Encrypt via Traefik) path completely untouched.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from hangar.auth.oidc import CLIENT_NAME, build_oauth, reset_oauth
from hangar.config import Settings, StartupError, set_settings, validate_startup

ISSUER = "https://idp.example.com"
DISCOVERY = f"{ISSUER}/.well-known/openid-configuration"


def _registered_client_kwargs(settings: Settings) -> dict:
    """The client_kwargs Authlib recorded for the registered OIDC client."""
    oauth = build_oauth(settings)
    _overwrite, kwargs = oauth._registry[CLIENT_NAME]
    return kwargs["client_kwargs"]


def _oidc_settings(**overrides: object) -> Settings:
    base: dict[str, object] = dict(
        access_mode_select="oidc",
        oidc_issuer=ISSUER,
        oidc_client_id="hangar",
        oidc_client_secret="shh",
        secret_key="k" * 32,
        oidc_redirect_url="https://hangar.example/auth/callback",
        session_cookie_secure=True,
    )
    base.update(overrides)
    return Settings(**base)


# --- the core guarantee: a real public cert (Let's Encrypt/Traefik) is unaffected ---


def test_default_leaves_tls_verification_untouched() -> None:
    """With no CA config, no `verify` override is passed — httpx keeps its certifi default,
    so a public-CA IdP (Let's Encrypt via Traefik) verifies exactly as before."""
    settings = _oidc_settings()
    assert settings.oidc_tls_verify is None  # "don't override"
    assert "verify" not in _registered_client_kwargs(settings)


def test_ca_bundle_is_threaded_into_the_client() -> None:
    settings = _oidc_settings(oidc_ca_bundle="/etc/ssl/internal-ca.pem")
    assert settings.oidc_tls_verify == "/etc/ssl/internal-ca.pem"
    assert _registered_client_kwargs(settings)["verify"] == "/etc/ssl/internal-ca.pem"


def test_verify_false_escape_hatch_disables_verification() -> None:
    settings = _oidc_settings(oidc_verify_ssl=False)
    assert settings.oidc_tls_verify is False
    assert _registered_client_kwargs(settings)["verify"] is False


def test_verify_false_wins_over_ca_bundle() -> None:
    settings = _oidc_settings(oidc_verify_ssl=False, oidc_ca_bundle="/etc/ssl/ca.pem")
    assert settings.oidc_tls_verify is False


# --- startup validation ---


def test_startup_warns_loudly_when_verification_disabled() -> None:
    warnings = validate_startup(_oidc_settings(oidc_verify_ssl=False))
    assert any("HANGAR_OIDC_VERIFY_SSL=false" in w for w in warnings)


def test_startup_fails_closed_on_missing_ca_bundle(tmp_path) -> None:
    missing = tmp_path / "nope.pem"
    with pytest.raises(StartupError, match="missing file"):
        validate_startup(_oidc_settings(oidc_ca_bundle=str(missing)))


def test_startup_accepts_an_existing_ca_bundle(tmp_path) -> None:
    ca = tmp_path / "ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n")
    warnings = validate_startup(_oidc_settings(oidc_ca_bundle=str(ca)))
    assert not any("HANGAR_OIDC_CA_BUNDLE" in w for w in warnings)  # no complaint


# --- graceful failure instead of a bare 500 ---


@respx.mock
def test_login_returns_502_when_idp_discovery_unreachable(monkeypatch) -> None:
    """A TLS/connect failure fetching discovery yields a clear 502, not an unhandled 500."""
    monkeypatch.setenv("HANGAR_ACCESS_MODE", "oidc")
    monkeypatch.setenv("HANGAR_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("HANGAR_OIDC_CLIENT_ID", "hangar")
    monkeypatch.setenv("HANGAR_OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setenv("HANGAR_SESSION_SECRET", "s" * 24)
    monkeypatch.setenv("HANGAR_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("HANGAR_OIDC_REDIRECT_URL", "http://testserver/auth/callback")
    monkeypatch.setenv("HANGAR_HOST", "127.0.0.1")
    monkeypatch.delenv("HANGAR_FORWARD_AUTH", raising=False)
    set_settings(Settings())
    reset_oauth()

    # Simulate the self-signed-cert case: the discovery fetch raises a TLS/connect error.
    respx.get(DISCOVERY).mock(
        side_effect=httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate")
    )

    from hangar.main import create_app

    try:
        with TestClient(create_app()) as client:
            resp = client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 502
        assert "identity provider" in resp.json()["detail"].lower()
    finally:
        reset_oauth()
