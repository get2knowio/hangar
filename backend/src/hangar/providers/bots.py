"""Dependency-update bot recognition — provider-neutral, single-sourced (Constitution I).

Both adapters classify a pull request by its author login so the aggregate ``bot_prs``
count and per-PR ``kind`` are computed identically across platforms. Each PR keeps its
real source (``dependabot`` | ``renovate`` | ``human``) — never lumped under one bot's
name (honest-state, Constitution VIII). Renovate runs on GitHub *and* Gitea, so this
lives outside any one provider package.
"""

from __future__ import annotations

# Recognized dependency-update bots, by author login.
_DEPENDABOT_LOGINS = ("dependabot[bot]", "dependabot-preview[bot]")
_RENOVATE_LOGINS = ("renovate[bot]", "renovate-bot")


def pr_kind(login: str | None) -> str:
    """Classify a PR by its author login: ``dependabot`` | ``renovate`` | ``human``."""
    if login in _DEPENDABOT_LOGINS:
        return "dependabot"
    if login in _RENOVATE_LOGINS:
        return "renovate"
    return "human"


def is_bot_login(login: str | None) -> bool:
    """True when the login is a recognized dependency-update bot (Dependabot or Renovate)."""
    return pr_kind(login) != "human"
