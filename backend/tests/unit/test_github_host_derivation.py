"""GitHub host derivation (multi-host: github.com, GHEC, GHES).

The provider seam turns a connection's opaque browser ``base_url`` into the REST API base
and the App-install path prefix. These are pure functions (no network), so they're unit
tested across all three host shapes — the core never learns any of this (Constitution I).
"""

from __future__ import annotations

import pytest

from hangar.domain.models import ProviderConnection
from hangar.providers.github.adapter import (
    GitHubAdapter,
    github_api_base,
    github_install_prefix,
    github_web_base,
)


@pytest.mark.parametrize(
    "base_url, api_base, install_prefix",
    [
        # github.com (and standard GHEC, which IS github.com)
        ("https://github.com", "https://api.github.com", "/apps"),
        ("https://github.com/", "https://api.github.com", "/apps"),  # trailing slash tolerated
        (None, "https://api.github.com", "/apps"),  # default
        # GHEC with data residency — tenant subdomain of ghe.com
        ("https://acme.ghe.com", "https://api.acme.ghe.com", "/apps"),
        ("https://octo-corp.ghe.com", "https://api.octo-corp.ghe.com", "/apps"),
        # GitHub Enterprise Server — arbitrary host, API under /api/v3, install under /github-apps
        ("https://ghe.example.com", "https://ghe.example.com/api/v3", "/github-apps"),
        ("https://git.internal.lan", "https://git.internal.lan/api/v3", "/github-apps"),
    ],
)
def test_host_derivation(base_url: str | None, api_base: str, install_prefix: str) -> None:
    assert github_api_base(base_url) == api_base
    assert github_install_prefix(base_url) == install_prefix


def test_web_base_strips_trailing_slash_and_defaults() -> None:
    assert github_web_base("https://ghe.example.com/") == "https://ghe.example.com"
    assert github_web_base(None) == "https://github.com"


def test_deep_link_and_pr_url_honor_enterprise_host() -> None:
    adapter = GitHubAdapter()
    conn = ProviderConnection(
        id="ghes",
        label="ghes:platform",
        provider_type="github",
        scope="org · platform",
        auth_mode="GitHub App",
        owner="platform",
        base_url="https://ghe.example.com",
    )
    from hangar.domain.models import Repo

    repo = Repo(id="api", connection_id="ghes", default_branch="main")
    assert adapter.deep_link(conn, repo, "branch_protection") == (
        "https://ghe.example.com/platform/api/settings/branches"
    )
    assert adapter.pr_url(conn, repo, 7) == "https://ghe.example.com/platform/api/pull/7"


def test_dotcom_connection_urls_unchanged() -> None:
    """A default (github.com) connection keeps its exact prior URLs — no regression."""
    adapter = GitHubAdapter()
    conn = ProviderConnection(
        id="gh",
        label="gh:get2knowio",
        provider_type="github",
        scope="org · get2knowio",
        auth_mode="GitHub App",
        owner="get2knowio",
    )
    from hangar.domain.models import Repo

    repo = Repo(id="hangar", connection_id="gh", default_branch="main")
    assert adapter.pr_url(conn, repo, 1) == "https://github.com/get2knowio/hangar/pull/1"
    assert github_api_base(conn.base_url) == "https://api.github.com"
