"""Regression: the GitHub adapter client is built with the resilience controls that keep
one slow/rate-limited connection from stalling or exhausting the poll cycle (Constitution
VI) — a bounded HTTP timeout, a concurrency throttler, and a rate-limit/5xx retry chain.
All are derived from settings (no platform constant hardcoded in core)."""

from __future__ import annotations

from hangar.config import Settings, set_settings
from hangar.domain.models import Capability, ProviderConnection
from hangar.providers.github.adapter import GitHubAdapter


def _token_connection() -> ProviderConnection:
    return ProviderConnection(
        id="gh-main", label="gh:acme", provider_type="github", scope="org",
        auth_mode="token", granted_capabilities={Capability.read_files},
        has_credential=True, token="ghp_fake_token",
    )


def test_client_applies_timeout_and_concurrency_from_settings(monkeypatch) -> None:
    monkeypatch.setenv("HANGAR_GITHUB_HTTP_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("HANGAR_GITHUB_MAX_CONCURRENCY", "4")
    set_settings(Settings())

    gh = GitHubAdapter()._client(_token_connection())

    assert gh.config.timeout.read == 12.5  # httpx.Timeout built from the configured float
    assert gh.config.throttler.max_concurrency == 4
    # Conditional requests are managed by hand, so the client cache stays off.
    assert gh.config.http_cache is False


def test_client_defaults_are_bounded_not_infinite() -> None:
    set_settings(Settings())  # no overrides → defaults

    gh = GitHubAdapter()._client(_token_connection())

    assert gh.config.timeout.read == 30.0
    assert gh.config.throttler.max_concurrency == 8


def test_client_retries_rate_limit_and_server_error() -> None:
    from githubkit.retry import RetryChainDecision

    set_settings(Settings())
    gh = GitHubAdapter()._client(_token_connection())

    # A retry chain (not the bare default) is wired so an exhausted rate-limit/secondary
    # limit or a transient 5xx backs off (honoring Retry-After) before the call gives up.
    assert isinstance(gh.config.auto_retry, RetryChainDecision)
