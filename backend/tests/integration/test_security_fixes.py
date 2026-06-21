"""Regression tests for review findings: SPA path traversal, webhook fail-closed,
least-privilege capability grant, constant-time proxy-secret compare."""

from __future__ import annotations

import os

from hangar.auth.forward_auth import _peer_trusted
from hangar.config import Settings
from hangar.main import safe_static_file


# --- SPA path traversal containment (main.safe_static_file) ---
def test_safe_static_file_blocks_traversal(tmp_path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>")
    (static / "app.js").write_text("ok")
    secret = tmp_path / "secret.txt"
    secret.write_text("SENTINEL")

    # legit asset resolves
    assert safe_static_file(str(static), "app.js") == os.path.realpath(str(static / "app.js"))
    # traversal escapes are rejected (None → caller serves index.html)
    for evil in ("../secret.txt", "../../secret.txt", "..%2f..%2fsecret.txt", "/etc/hostname"):
        assert safe_static_file(str(static), evil) is None, evil
    # a non-existent in-tree path is also None
    assert safe_static_file(str(static), "nope.js") is None


# --- Webhook fail-closed + signature enforcement ---
def test_webhook_refused_without_secret(client) -> None:
    # Default test settings have no HANGAR_WEBHOOK_SECRET → endpoint fails closed (503),
    # never accepting an unsigned mutation.
    r = client.post("/api/v1/webhooks/gh-main", json={"repository": {"name": "hangar"},
                                                       "check_suite": {"conclusion": "success"}})
    assert r.status_code == 503
    assert r.json()["accepted"] is False


def test_webhook_rejects_bad_signature(monkeypatch, client) -> None:
    import hashlib
    import hmac
    import json

    from hangar.config import get_settings

    get_settings().webhook_secret = "shh"
    try:
        body = json.dumps({"repository": {"name": "hangar"}, "pull_request": {}}).encode()
        # wrong signature → 401
        bad = client.post("/api/v1/webhooks/gh-main", content=body,
                          headers={"X-Hub-Signature-256": "sha256=deadbeef", "X-GitHub-Event": "pull_request"})
        assert bad.status_code == 401
        # correct signature → accepted
        sig = "sha256=" + hmac.new(b"shh", body, hashlib.sha256).hexdigest()
        ok = client.post("/api/v1/webhooks/gh-main", content=body,
                         headers={"X-Hub-Signature-256": sig, "X-GitHub-Event": "pull_request"})
        assert ok.status_code == 200
    finally:
        get_settings().webhook_secret = None


# --- Least-privilege capability grant on add_connection ---
def test_added_connection_is_read_only_by_default(client) -> None:
    client.post("/api/v1/providers", json={
        "provider_type": "github", "label": "gh:readonly", "scope": "org · 1 repos",
        "credential": "ghp_readonly",
    })
    cards = client.get("/api/v1/providers").json()["connections"]
    added = next(c for c in cards if c["label"] == "gh:readonly")
    assert added["writes"] is False
    assert added["write_label"] == "Read-only"


def test_added_connection_writable_only_when_declared(client) -> None:
    client.post("/api/v1/providers", json={
        "provider_type": "github", "label": "gh:writer", "scope": "org · 1 repos",
        "credential": "ghp_writer", "writable": True,
    })
    cards = client.get("/api/v1/providers").json()["connections"]
    added = next(c for c in cards if c["label"] == "gh:writer")
    assert added["writes"] is True


# --- Proxy-secret trust is constant-time and fails closed ---
def test_peer_trust_requires_configured_trust() -> None:
    from starlette.requests import Request

    settings = Settings(forward_auth="enabled")  # no CIDR, no secret
    scope = {"type": "http", "headers": [(b"x-hangar-proxy-secret", b"anything")], "client": ("9.9.9.9", 1)}
    req = Request(scope)
    assert _peer_trusted(req, settings) is False  # fail closed when nothing is configured
