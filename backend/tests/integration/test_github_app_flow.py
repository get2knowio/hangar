"""End-to-end "Connect with GitHub" App manifest + install flow (#25).

respx intercepts the app's *outbound* GitHub calls (manifest conversion, installation
lookup, installation-token mint, repo listing); the TestClient→app calls go through
ASGITransport untouched, so the signed session cookie carries the CSRF ``state`` across the
three browser-redirect hops exactly as in production. A real RSA key is generated so
githubkit's App-JWT signing runs for real against the stubbed HTTP.

Covers github.com and GHES host derivation, the "selected repos" allowlist, CSRF rejection
on both callbacks, App-reuse-on-second-connect, and that secrets never leak into reads.
"""

from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from hangar.config import Settings, set_settings
from hangar.persistence.crypto import decrypt
from hangar.persistence.db import get_sessionmaker
from hangar.persistence.models import GitHubAppRegistration


@pytest.fixture
def gh_client(monkeypatch) -> TestClient:
    """A TestClient whose session cookie rides plain http (the flow spans GET redirects).

    Without ``HANGAR_SESSION_COOKIE_SECURE=false`` the signed session cookie is marked
    Secure and the TestClient (http://testserver) never sends it back — the CSRF ``state``
    would be lost between hops. HANGAR_BASE_URL pins the manifest callback host.
    """
    monkeypatch.setenv("HANGAR_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("HANGAR_BASE_URL", "http://testserver")
    set_settings(Settings())
    from hangar.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def app_pem() -> str:
    """A real RSA private key, as a PEM — what the manifest conversion 'returns'."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _state_from(text_or_url: str) -> str:
    m = re.search(r"state=([A-Za-z0-9_\-]+)", text_or_url)
    assert m, f"no state in: {text_or_url[:200]}"
    return m.group(1)


def _manifest_from_form(html: str) -> dict:
    """Pull the manifest JSON back out of the /new auto-submit form's hidden input."""
    m = re.search(r'name="manifest" value="(.*?)">', html, re.DOTALL)
    assert m, f"no manifest input in: {html[:200]}"
    return json.loads(unescape(m.group(1)))


def _connected_id(resp: httpx.Response) -> str:
    """The new connection id from the final ``/providers?connected=<id>`` redirect."""
    assert resp.headers["location"].startswith("/providers?connected=")
    return parse_qs(urlparse(resp.headers["location"]).query)["connected"][0]


def _card(client: TestClient, conn_id: str) -> dict:
    cards = client.get("/api/v1/providers").json()["connections"]
    return next(c for c in cards if c["id"] == conn_id)


def _stub_conversion(router: respx.MockRouter, api: str, code: str, pem: str) -> None:
    router.post(f"{api}/app-manifests/{code}/conversions").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 123456,
                "slug": "hangar-test",
                "client_id": "Iv1.abc123",
                "client_secret": "supersecret-client",
                "webhook_secret": "supersecret-webhook",
                "pem": pem,
            },
        )
    )


def _stub_installation(
    router: respx.MockRouter, api: str, install_id: int, *, selection: str, owner: str
) -> None:
    router.get(f"{api}/app/installations/{install_id}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": install_id,
                "account": {"login": owner, "type": "Organization"},
                "repository_selection": selection,
            },
        )
    )
    if selection == "selected":
        # AppInstallationAuthStrategy mints an installation token, then lists the repos.
        router.post(f"{api}/app/installations/{install_id}/access_tokens").mock(
            return_value=httpx.Response(
                201, json={"token": "ghs_installtoken", "expires_at": "2099-01-01T00:00:00Z"}
            )
        )
        router.get(f"{api}/installation/repositories").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total_count": 2,
                    "repositories": [{"name": "api"}, {"name": "web"}],
                },
            )
        )


def _drive_flow(
    gh_client: TestClient,
    router: respx.MockRouter,
    *,
    base_url: str,
    api: str,
    pem: str,
    owner: str = "test-org",
    selection: str = "all",
    install_id: int = 42,
) -> httpx.Response:
    """Run /new → /created → /installed; return the final (install) response."""
    # 1) /new — HTML auto-submit form carrying the CSRF state.
    r = gh_client.get(
        "/api/v1/providers/github/app/new",
        params={"base_url": base_url, "writable": "true"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    state = _state_from(r.text)
    assert f"{base_url}/settings/apps/new" in r.text  # posts the manifest to the right host

    # 2) /created — exchange the manifest code; redirect to the install page.
    _stub_conversion(router, api, "thecode", pem)
    r = gh_client.get(
        "/api/v1/providers/github/app/created",
        params={"code": "thecode", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 303
    install_loc = r.headers["location"]
    state2 = _state_from(install_loc)

    # 3) /installed — resolve the installation and create the connection.
    _stub_installation(router, api, install_id, selection=selection, owner=owner)
    return gh_client.get(
        "/api/v1/providers/github/app/installed",
        params={"installation_id": install_id, "setup_action": "install", "state": state2},
        follow_redirects=False,
    )


def test_manifest_is_private_by_default(gh_client) -> None:
    """Least-privilege default: the App is registered private (owner-account installs only)."""
    r = gh_client.get(
        "/api/v1/providers/github/app/new",
        params={"base_url": "https://github.com"},
        follow_redirects=False,
    )
    assert _manifest_from_form(r.text)["public"] is False


def test_manifest_public_when_env_set(monkeypatch) -> None:
    """HANGAR_GITHUB_APP_PUBLIC=true registers the App public so orgs can install it (#40+)."""
    monkeypatch.setenv("HANGAR_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("HANGAR_BASE_URL", "http://testserver")
    monkeypatch.setenv("HANGAR_GITHUB_APP_PUBLIC", "true")
    set_settings(Settings())
    from hangar.main import create_app

    with TestClient(create_app()) as c:
        r = c.get(
            "/api/v1/providers/github/app/new",
            params={"base_url": "https://github.com"},
            follow_redirects=False,
        )
    assert _manifest_from_form(r.text)["public"] is True


def test_dotcom_flow_creates_connection(gh_client, app_pem) -> None:
    with respx.mock(assert_all_called=False) as router:
        r = _drive_flow(
            gh_client, router, base_url="https://github.com", api="https://api.github.com",
            pem=app_pem, owner="get2knowio", selection="all",
        )
    assert r.status_code == 303
    conn_id = _connected_id(r)

    # The connection is real, App-authed, writable, and watching all repos.
    conn = _card(gh_client, conn_id)
    assert conn["label"] == "gh:get2knowio"
    assert conn["base_url"] == "https://github.com"
    assert conn["writes"] is True
    assert conn["repo_allowlist"] is None  # selection=all ⇒ watch everything
    assert conn["has_credential"] is True

    # Nothing in the read response leaks the PEM / gh_client / webhook secret.
    blob = gh_client.get("/api/v1/providers").text
    for secret in ("BEGIN PRIVATE KEY", "supersecret-client", "supersecret-webhook", app_pem[:40]):
        assert secret not in blob


def test_selected_repos_become_allowlist(gh_client, app_pem) -> None:
    with respx.mock(assert_all_called=False) as router:
        r = _drive_flow(
            gh_client, router, base_url="https://github.com", api="https://api.github.com",
            pem=app_pem, owner="acme", selection="selected",
        )
    assert r.status_code == 303
    conn = _card(gh_client, _connected_id(r))
    assert conn["label"] == "gh:acme"
    assert sorted(conn["repo_allowlist"]) == ["api", "web"]


def test_ghes_flow_uses_enterprise_urls(gh_client, app_pem) -> None:
    base = "https://ghe.example.com"
    api = "https://ghe.example.com/api/v3"
    with respx.mock(assert_all_called=False) as router:
        # /new for GHES points the manifest at the GHES host and install at /github-apps.
        rnew = gh_client.get(
            "/api/v1/providers/github/app/new",
            params={"base_url": base, "writable": "true"},
            follow_redirects=False,
        )
        assert f"{base}/settings/apps/new" in rnew.text
        state = _state_from(rnew.text)
        _stub_conversion(router, api, "c", app_pem)
        rcre = gh_client.get(
            "/api/v1/providers/github/app/created",
            params={"code": "c", "state": state},
            follow_redirects=False,
        )
        install_loc = rcre.headers["location"]
        assert install_loc.startswith(f"{base}/github-apps/")  # GHES install path
        _stub_installation(router, api, 7, selection="all", owner="platform")
        rins = gh_client.get(
            "/api/v1/providers/github/app/installed",
            params={"installation_id": 7, "state": _state_from(install_loc)},
            follow_redirects=False,
        )
    assert rins.status_code == 303
    conn = _card(gh_client, _connected_id(rins))
    assert conn["base_url"] == base and conn["label"] == "gh:platform"


def test_app_registration_stored_encrypted(gh_client, app_pem) -> None:
    async def _read_reg() -> GitHubAppRegistration | None:
        async with get_sessionmaker()() as s:
            return await s.get(GitHubAppRegistration, "https://github.com")

    with respx.mock(assert_all_called=False) as router:
        _drive_flow(
            gh_client, router, base_url="https://github.com", api="https://api.github.com",
            pem=app_pem, owner="x", selection="all",
        )
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        reg = loop.run_until_complete(_read_reg())
    finally:
        loop.close()
    assert reg is not None
    # Ciphertext at rest (not plaintext) and decryptable back to the issued PEM.
    assert b"BEGIN PRIVATE KEY" not in reg.private_key_ciphertext
    assert decrypt(reg.private_key_ciphertext) == app_pem
    assert decrypt(reg.client_secret_ciphertext) == "supersecret-client"
    assert decrypt(reg.webhook_secret_ciphertext) == "supersecret-webhook"


def test_second_connect_reuses_existing_app(gh_client, app_pem) -> None:
    """A second Connect on the same host skips creation and jumps straight to install."""
    with respx.mock(assert_all_called=False) as router:
        _drive_flow(
            gh_client, router, base_url="https://github.com", api="https://api.github.com",
            pem=app_pem, owner="first", selection="all", install_id=1,
        )
        # Now /new should 303 straight to the install URL (no manifest form).
        r = gh_client.get(
            "/api/v1/providers/github/app/new",
            params={"base_url": "https://github.com"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "/apps/hangar-test/installations/new" in r.headers["location"]


def _stub_uninstall_one(
    router: respx.MockRouter, api: str, install_id: int, *, delete_status: int = 204
) -> None:
    """Stub the single-installation uninstall (DELETE) a per-connection removal issues.

    The GET /app/installations/{id} lookup is already stubbed by ``_drive_flow`` (via
    ``_stub_installation``); the removal only additionally needs the DELETE.
    """
    router.delete(f"{api}/app/installations/{install_id}").mock(
        return_value=httpx.Response(delete_status)
    )


def _install_again(
    gh_client: TestClient,
    router: respx.MockRouter,
    *,
    base_url: str,
    api: str,
    owner: str,
    install_id: int,
) -> httpx.Response:
    """Install the *already-registered* App on a second org (reuse path: /new → 303 install)."""
    r = gh_client.get(
        "/api/v1/providers/github/app/new",
        params={"base_url": base_url, "writable": "true"},
        follow_redirects=False,
    )
    assert r.status_code == 303  # existing App → straight to install, no manifest conversion
    state = _state_from(r.headers["location"])
    _stub_installation(router, api, install_id, selection="all", owner=owner)
    return gh_client.get(
        "/api/v1/providers/github/app/installed",
        params={"installation_id": install_id, "state": state},
        follow_redirects=False,
    )


def test_remove_last_org_uninstalls_and_returns_delete_link(gh_client, app_pem) -> None:
    """Removing the App's LAST connection uninstalls that org, forgets the App, and hands back
    the delete-App deep link (GitHub has no delete-App API)."""
    with respx.mock(assert_all_called=False) as router:
        r = _drive_flow(
            gh_client, router, base_url="https://github.com", api="https://api.github.com",
            pem=app_pem, owner="get2knowio", selection="all", install_id=42,
        )
        conn_id = _connected_id(r)
        _stub_uninstall_one(router, "https://api.github.com", 42)
        dr = gh_client.delete(f"/api/v1/providers/{conn_id}")

    assert dr.status_code == 200
    body = dr.json()
    assert body["removed"] is True
    assert body["uninstalled"] is True
    assert body["app_forgotten"] is True
    assert body["delete_app_url"] == "https://github.com/settings/apps/hangar-test/advanced"
    assert body["uninstall_url"] is None

    # The connection is gone and the registration is forgotten (no longer surfaced).
    after = gh_client.get("/api/v1/providers").json()
    assert all(c["id"] != conn_id for c in after["connections"])
    assert after["app_registrations"] == []


def test_remove_one_org_keeps_the_app_for_siblings(gh_client, app_pem) -> None:
    """Removing a non-last org drops just that row + uninstalls it; the App and the other org's
    connection survive (no delete-App link, registration retained)."""
    api = "https://api.github.com"
    with respx.mock(assert_all_called=False) as router:
        r_a = _drive_flow(
            gh_client, router, base_url="https://github.com", api=api,
            pem=app_pem, owner="get2knowio", selection="all", install_id=42,
        )
        conn_a = _connected_id(r_a)
        r_b = _install_again(
            gh_client, router, base_url="https://github.com", api=api, owner="acme", install_id=43,
        )
        conn_b = _connected_id(r_b)

        _stub_uninstall_one(router, api, 42)
        dr = gh_client.delete(f"/api/v1/providers/{conn_a}")

    assert dr.status_code == 200
    body = dr.json()
    assert body["removed"] is True
    assert body["uninstalled"] is True
    assert body["app_forgotten"] is False  # acme still uses the App
    assert body["delete_app_url"] is None

    after = gh_client.get("/api/v1/providers").json()
    assert all(c["id"] != conn_a for c in after["connections"])
    assert any(c["id"] == conn_b for c in after["connections"])  # sibling survives
    assert any(reg["slug"] == "hangar-test" for reg in after["app_registrations"])  # App kept


def test_remove_tolerates_already_uninstalled(gh_client, app_pem) -> None:
    """A 404 on DELETE (installation already gone) still counts as uninstalled — idempotent."""
    with respx.mock(assert_all_called=False) as router:
        r = _drive_flow(
            gh_client, router, base_url="https://github.com", api="https://api.github.com",
            pem=app_pem, owner="acme", selection="all", install_id=7,
        )
        conn_id = _connected_id(r)
        _stub_uninstall_one(router, "https://api.github.com", 7, delete_status=404)
        dr = gh_client.delete(f"/api/v1/providers/{conn_id}")
    assert dr.status_code == 200
    body = dr.json()
    assert body["uninstalled"] is True
    assert body["app_forgotten"] is True


def test_remove_unknown_connection_is_404(gh_client) -> None:
    assert gh_client.delete("/api/v1/providers/does-not-exist").status_code == 404


def test_created_rejects_bad_state(gh_client) -> None:
    # Start the flow so a session state exists, then submit a forged state (CSRF).
    gh_client.get(
        "/api/v1/providers/github/app/new",
        params={"base_url": "https://github.com"},
        follow_redirects=False,
    )
    r = gh_client.get(
        "/api/v1/providers/github/app/created",
        params={"code": "x", "state": "forged"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_installed_rejects_bad_state(gh_client) -> None:
    gh_client.get(
        "/api/v1/providers/github/app/new",
        params={"base_url": "https://github.com"},
        follow_redirects=False,
    )
    r = gh_client.get(
        "/api/v1/providers/github/app/installed",
        params={"installation_id": 1, "state": "forged"},
        follow_redirects=False,
    )
    assert r.status_code == 400
