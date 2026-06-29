"""PR author classification: Dependabot and Renovate are both dependency bots, labelled by
their real source (honest-state). Pure functions — no network."""

from __future__ import annotations

import pytest

from hangar.providers.github.detection import is_bot_login, pr_kind


@pytest.mark.parametrize(
    "login, kind",
    [
        ("dependabot[bot]", "dependabot"),
        ("dependabot-preview[bot]", "dependabot"),
        ("renovate[bot]", "renovate"),
        ("renovate-bot", "renovate"),
        ("octocat", "human"),
        (None, "human"),
    ],
)
def test_pr_kind(login: str | None, kind: str) -> None:
    assert pr_kind(login) == kind


def test_is_bot_login() -> None:
    assert is_bot_login("renovate[bot]") is True
    assert is_bot_login("dependabot[bot]") is True
    assert is_bot_login("octocat") is False
    assert is_bot_login(None) is False
