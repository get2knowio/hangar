"""Webhook HMAC signature verification (FR-033) — now behind the provider seam."""

from __future__ import annotations

import hashlib
import hmac

from hangar.providers.github.adapter import GitHubAdapter

_SECRET = "webhook-secret"
_BODY = b'{"action":"opened"}'
_adapter = GitHubAdapter()


def _hdr(sig: str | None) -> dict[str, str]:
    return {"X-Hub-Signature-256": sig} if sig is not None else {}


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_accepts_correct_signature() -> None:
    assert _adapter.verify_webhook(_hdr(_sign(_SECRET, _BODY)), _BODY, _SECRET) is True


def test_rejects_forged_signature() -> None:
    assert _adapter.verify_webhook(_hdr("sha256=" + "0" * 64), _BODY, _SECRET) is False


def test_rejects_wrong_secret() -> None:
    assert _adapter.verify_webhook(_hdr(_sign("other-secret", _BODY)), _BODY, _SECRET) is False


def test_rejects_missing_signature() -> None:
    assert _adapter.verify_webhook(_hdr(None), _BODY, _SECRET) is False
    assert _adapter.verify_webhook(_hdr(""), _BODY, _SECRET) is False


def test_rejects_unprefixed_signature() -> None:
    raw = hmac.new(_SECRET.encode(), _BODY, hashlib.sha256).hexdigest()
    assert _adapter.verify_webhook(_hdr(raw), _BODY, _SECRET) is False


def test_parse_webhook_normalizes_ci_and_pr_events() -> None:
    import json

    ci = _adapter.parse_webhook(
        {"X-GitHub-Event": "check_suite"},
        json.dumps({"repository": {"name": "r"}, "check_suite": {"conclusion": "failure"}}).encode(),
    )
    assert ci is not None and ci.repo_name == "r" and ci.ci_status == "fail"

    pr = _adapter.parse_webhook(
        {"X-GitHub-Event": "pull_request"},
        json.dumps(
            {"repository": {"name": "r"}, "action": "opened",
             "pull_request": {"user": {"login": "dependabot[bot]"}}}
        ).encode(),
    )
    assert pr is not None and pr.pr_delta == 1 and pr.pr_is_bot is True
