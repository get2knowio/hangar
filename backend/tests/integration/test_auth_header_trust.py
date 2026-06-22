"""T068 — forward-auth header trust: forged headers rejected, proxy-trusted admitted (SC-007)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from hangar.auth.forward_auth import _peer_trusted
from hangar.config import Settings, set_settings


@pytest.fixture
def forward_auth_app(monkeypatch):
    """Build an app in forward-auth mode trusting a proxy secret."""
    monkeypatch.setenv("HANGAR_FORWARD_AUTH", "enabled")
    monkeypatch.setenv("HANGAR_TRUSTED_PROXY_SECRET", "s3cr3t-proxy")
    monkeypatch.setenv("HANGAR_FORWARD_AUTH_USER_HEADER", "Remote-User")
    monkeypatch.setenv("HANGAR_HOST", "127.0.0.1")
    monkeypatch.delenv("HANGAR_TRUSTED_PROXY_CIDR", raising=False)
    monkeypatch.delenv("HANGAR_FORWARD_AUTH_ALLOWED_USER", raising=False)
    set_settings(Settings())
    from hangar.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_forged_identity_header_without_trust_rejected(forward_auth_app) -> None:
    # No proxy secret → peer is untrusted → 403 even with an identity header.
    r = forward_auth_app.get("/api/v1/me", headers={"Remote-User": "attacker"})
    assert r.status_code == 403


def test_trusted_proxy_secret_admits_and_me_reflects_identity(forward_auth_app) -> None:
    r = forward_auth_app.get(
        "/api/v1/me",
        headers={"X-Hangar-Proxy-Secret": "s3cr3t-proxy", "Remote-User": "alice"},
    )
    assert r.status_code == 200
    assert r.json()["actor"] == "alice"


def test_trusted_peer_missing_identity_is_401(forward_auth_app) -> None:
    r = forward_auth_app.get("/api/v1/me", headers={"X-Hangar-Proxy-Secret": "s3cr3t-proxy"})
    assert r.status_code == 401


def _fake_request(client_host: str | None, headers: dict[str, str] | None = None):
    return SimpleNamespace(
        client=SimpleNamespace(host=client_host) if client_host else None,
        headers=headers or {},
    )


def test_peer_trusted_helper_cidr() -> None:
    settings = Settings(forward_auth="enabled", trusted_proxy_cidr="127.0.0.1/32")
    assert _peer_trusted(_fake_request("127.0.0.1"), settings) is True
    assert _peer_trusted(_fake_request("10.0.0.5"), settings) is False


def test_peer_trusted_helper_secret() -> None:
    settings = Settings(forward_auth="enabled", trusted_proxy_secret="abc")
    trusted = _fake_request("10.0.0.5", {"X-Hangar-Proxy-Secret": "abc"})
    assert _peer_trusted(trusted, settings) is True
    forged = _fake_request("10.0.0.5", {"X-Hangar-Proxy-Secret": "wrong"})
    assert _peer_trusted(forged, settings) is False


def test_peer_trusted_no_trust_config_is_false() -> None:
    settings = Settings(forward_auth="enabled")
    assert _peer_trusted(_fake_request("127.0.0.1"), settings) is False
