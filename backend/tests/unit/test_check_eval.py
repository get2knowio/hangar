"""T021 — Check evaluation semantics: pass/fail/unknown, hygiene math, catalog shape."""

from __future__ import annotations

from hangar.domain.checks import CATALOG, GROUPS, all_checks
from hangar.domain.models import FindingStatus, RemediationState, Repo
from hangar.domain.policy import (
    default_policy,
    effective_status,
    enabled_checks,
    hygiene,
)


def _repo(fails=None, unknowns=None) -> Repo:
    return Repo(id="r1", connection_id="c1", fails=fails or [], unknowns=unknowns or [])


def test_catalog_has_exactly_23_checks() -> None:
    assert len(CATALOG) == 23
    assert len(all_checks()) == 23


def test_groups_are_five_and_cover_all_checks() -> None:
    assert len(GROUPS) == 5
    grouped = [c for c in all_checks()]
    assert {c.group for c in grouped} == set(GROUPS)
    # every catalog check belongs to one of the 5 groups
    assert all(c.group in GROUPS for c in CATALOG.values())


def test_effective_status_pass_fail_unknown() -> None:
    repo = _repo(fails=["license"], unknowns=["two_fa"])
    assert effective_status(repo, "license") is FindingStatus.fail
    assert effective_status(repo, "two_fa") is FindingStatus.unknown
    # a check neither failing nor unknown passes
    passing_check = next(c.id for c in all_checks() if c.id not in ("license", "two_fa"))
    assert effective_status(repo, passing_check) is FindingStatus.passing


def test_remediation_overlay_changes_status() -> None:
    repo = _repo(fails=["license"])
    key = (repo.connection_id, repo.id, "license")
    base = {key: RemediationState.working}
    assert effective_status(repo, "license", base) is FindingStatus.working

    pr_open = {key: RemediationState.pr_open}
    assert effective_status(repo, "license", pr_open) is FindingStatus.pending

    fixed = {key: RemediationState.fixed}
    assert effective_status(repo, "license", fixed) is FindingStatus.passing


def test_hygiene_rollup_math() -> None:
    policy = default_policy()
    total = len(enabled_checks(policy))
    assert total == 23

    clean = _repo()
    assert hygiene(clean, policy) == 100

    one_fail = _repo(fails=["license"])
    expected = round((total - 1) / total * 100)
    assert hygiene(one_fail, policy) == expected

    # a fixed remediation restores that check to passing → back to 100
    fixed_map = {(one_fail.connection_id, one_fail.id, "license"): RemediationState.fixed}
    assert hygiene(one_fail, policy, fixed_map) == 100


def test_hygiene_unknown_counts_as_not_passing() -> None:
    policy = default_policy()
    total = len(enabled_checks(policy))
    repo = _repo(unknowns=["two_fa"])
    expected = round((total - 1) / total * 100)
    assert hygiene(repo, policy) == expected
