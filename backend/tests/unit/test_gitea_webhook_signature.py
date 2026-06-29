"""Gitea webhook HMAC verification + event parsing (FR-033) — behind the provider seam.

Gitea differs from GitHub: the signature rides ``X-Gitea-Signature`` as a **raw hex**
HMAC-SHA256 digest (no ``sha256=`` prefix), and events arrive under ``X-Gitea-Event``.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from hangar.providers.gitea.adapter import GiteaAdapter

_SECRET = "webhook-secret"
_BODY = b'{"action":"opened"}'
_adapter = GiteaAdapter()


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _hdr(sig: str | None) -> dict[str, str]:
    return {"X-Gitea-Signature": sig} if sig is not None else {}


def test_accepts_correct_raw_hex_signature() -> None:
    assert _adapter.verify_webhook(_hdr(_sign(_SECRET, _BODY)), _BODY, _SECRET) is True


def test_rejects_forged_signature() -> None:
    assert _adapter.verify_webhook(_hdr("0" * 64), _BODY, _SECRET) is False


def test_rejects_wrong_secret() -> None:
    assert _adapter.verify_webhook(_hdr(_sign("other-secret", _BODY)), _BODY, _SECRET) is False


def test_rejects_missing_signature_or_secret() -> None:
    assert _adapter.verify_webhook(_hdr(None), _BODY, _SECRET) is False
    assert _adapter.verify_webhook(_hdr(""), _BODY, _SECRET) is False
    assert _adapter.verify_webhook(_hdr(_sign(_SECRET, _BODY)), _BODY, "") is False


def test_rejects_github_style_sha256_prefixed_signature() -> None:
    # A GitHub-format "sha256=<hex>" value must NOT validate against Gitea's raw-hex scheme.
    assert _adapter.verify_webhook(_hdr("sha256=" + _sign(_SECRET, _BODY)), _BODY, _SECRET) is False


def test_parse_webhook_normalizes_ci_and_pr_events() -> None:
    ci = _adapter.parse_webhook(
        {"X-Gitea-Event": "status"},
        json.dumps({"repository": {"name": "r"}, "state": "failure"}).encode(),
    )
    assert ci is not None and ci.repo_name == "r" and ci.ci_status == "fail"

    pr = _adapter.parse_webhook(
        {"X-Gitea-Event": "pull_request"},
        json.dumps({"repository": {"name": "r"}, "action": "opened",
                    "pull_request": {"user": {"login": "renovate[bot]"}}}).encode(),
    )
    assert pr is not None and pr.pr_delta == 1 and pr.pr_is_bot is True


def test_parse_webhook_recognizes_humans_and_close() -> None:
    def _pr(login: str, action: str = "opened"):
        return _adapter.parse_webhook(
            {"X-Gitea-Event": "pull_request"},
            json.dumps({"repository": {"name": "r"}, "action": action,
                        "pull_request": {"user": {"login": login}}}).encode(),
        )

    assert _pr("octocat").pr_is_bot is False
    assert _pr("renovate[bot]", "closed").pr_delta == -1
    # An unactionable PR action (e.g. synchronize) is ignored.
    assert _pr("octocat", "synchronize") is None
