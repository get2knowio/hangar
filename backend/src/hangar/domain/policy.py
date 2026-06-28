"""Policy construction + the evaluation engine (FR-005–FR-007, FR-019).

This is the provider-neutral scoring core. It mirrors the prototype's ``buildPolicy``,
``effStatus``, ``hygiene`` and roll-up logic exactly so the shipped scorecard matches
``docs/prototype/Hangar.dc.html``. Remediation state overlays the raw finding: an
in-flight correction shows ``working``; an open Hangar PR shows ``pending``; a merged/
applied correction shows ``pass`` (FR-005a).
"""

from __future__ import annotations

from hangar.domain.checks import CATALOG, all_checks
from hangar.domain.models import (
    Check,
    FindingStatus,
    Policy,
    PolicyEntry,
    RemediationState,
    Repo,
    Tone,
)

# (connection_id, repo_id, check_id) -> RemediationState. Connection-scoped so a fix on
# one connection's repo never overlays a same-named repo under another connection.
RemediationMap = dict[tuple[str, str, str], RemediationState]


def default_policy() -> Policy:
    """All catalog checks enabled; targets seeded from each check's default (prototype ``buildPolicy``)."""
    entries = [
        PolicyEntry(
            check_id=c.id,
            enabled=True,
            params={"target": c.default_target} if c.default_target is not None else {},
        )
        for c in all_checks()
    ]
    return Policy(id="default", name="Fleet baseline", entries=entries)


def enabled_checks(policy: Policy) -> list[Check]:
    return [c for c in all_checks() if policy.is_enabled(c.id)]


def effective_status(
    repo: Repo, check_id: str, remediations: RemediationMap | None = None
) -> FindingStatus:
    """Effective status incl. remediation overlay (prototype ``effStatus``)."""
    rem = (remediations or {}).get((repo.connection_id, repo.id, check_id))
    if rem is not None:
        if rem is RemediationState.fixed:
            return FindingStatus.passing
        if rem is RemediationState.working:
            return FindingStatus.working
        if rem is RemediationState.pr_open:
            return FindingStatus.pending
    if check_id in repo.fails:
        return FindingStatus.fail
    if check_id in repo.unknowns:
        return FindingStatus.unknown
    return FindingStatus.passing


def hygiene(repo: Repo, policy: Policy, remediations: RemediationMap | None = None) -> int:
    """Passing enabled checks ÷ enabled checks, as a percent (prototype ``hygiene``)."""
    checks = enabled_checks(policy)
    if not checks:
        return 100
    passing = sum(
        1 for c in checks if effective_status(repo, c.id, remediations) is FindingStatus.passing
    )
    return round(passing / len(checks) * 100)


def pass_count(repo: Repo, policy: Policy, remediations: RemediationMap | None = None) -> int:
    return sum(
        1
        for c in enabled_checks(policy)
        if effective_status(repo, c.id, remediations) is FindingStatus.passing
    )


def hygiene_tone(pct: int) -> Tone:
    """Hygiene color thresholds (prototype ``hygColor``): ≥85 pass, ≥65 warn, else fail."""
    if pct >= 85:
        return Tone.passing
    if pct >= 65:
        return Tone.warn
    return Tone.fail


def evidence_for(repo: Repo, check_id: str, status: FindingStatus) -> str:
    """Human evidence string for a finding (prototype ``EVID`` + unknown handling)."""
    if status is FindingStatus.unknown:
        return "Insufficient scope on this connection"
    if status in (FindingStatus.fail,):
        check = CATALOG.get(check_id)
        return check.evidence_fail if check else "Not detected"
    if status is FindingStatus.working:
        return "Submitting correction…"
    if status is FindingStatus.pending:
        return "Correction opened as a pull request"
    # Enrich the passing license finding with the detected SPDX id (e.g. "MIT") when known.
    if check_id == "license" and repo.license_spdx:
        return repo.license_spdx
    return "Detected"
