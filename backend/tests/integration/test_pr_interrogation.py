"""Open-PR interrogation — the presenter shows real cached PRs, never fabricated ones."""

from __future__ import annotations

from hangar.domain.models import ProviderConnection, PullRequestSummary, Repo
from hangar.domain.policy import default_policy
from hangar.services.repo_detail import _pr_list, build_repo_detail


def _repo_with_prs() -> Repo:
    return Repo(
        id="r", connection_id="c", open_prs=2, dependabot_prs=1,
        pull_requests=[
            PullRequestSummary(title="Bump vite", kind="dependabot", url="http://x/pull/7",
                               draft=False, created_at="2024-01-01T00:00:00Z"),
            PullRequestSummary(title="WIP feature", kind="human", url="http://x/pull/6",
                               draft=True, created_at="2024-01-02T00:00:00Z"),
        ],
    )


def test_real_cached_prs_are_rendered() -> None:
    rows = _pr_list(_repo_with_prs(), synthesize=True)  # real data wins even for demo
    assert [r["title"] for r in rows] == ["Bump vite", "WIP feature"]
    assert rows[0]["status"] == "open" and rows[0]["url"] == "http://x/pull/7"
    assert rows[1]["status"] == "draft"


def test_no_rows_for_live_connection_without_cached_prs() -> None:
    repo = Repo(id="r", connection_id="c", open_prs=3, dependabot_prs=1)  # no captured PRs
    assert _pr_list(repo, synthesize=False) == []


def test_synthetic_rows_only_for_demo_without_real_data() -> None:
    repo = Repo(id="r", connection_id="c", open_prs=2, dependabot_prs=1)
    assert len(_pr_list(repo, synthesize=True)) == 2


def test_repo_detail_exposes_real_pr_urls() -> None:
    conn = ProviderConnection(
        id="c", label="gh:acme", provider_type="github", scope="org", auth_mode="App",
        has_credential=True,
    )
    detail = build_repo_detail(_repo_with_prs(), conn, default_policy(), {}, {}, {})
    assert detail["pull_requests"][0]["url"] == "http://x/pull/7"
    assert detail["pull_requests"][0]["status"] == "open"
