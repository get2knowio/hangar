"""Release-automation checks (group: Release)."""

from __future__ import annotations

from hangar.domain.models import Check, RemediationTier

from ._caps import caps_for_tier

_G = "Release"

CHECKS: list[Check] = [
    Check(
        id="release_please", label="release-please configured", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        evidence_fail="No release-please manifest",
    ),
    Check(
        id="conventional", label="Conventional commits enforced", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="No commitlint / PR-title workflow",
    ),
    Check(
        id="changelog", label="CHANGELOG automated", group=_G,
        tier=RemediationTier.report, required_capabilities=caps_for_tier(RemediationTier.report),
        evidence_fail="No CHANGELOG.md / release notes",
    ),
    Check(
        id="release_health", label="Release health / commit age", group=_G,
        tier=RemediationTier.report, required_capabilities=caps_for_tier(RemediationTier.report),
        evidence_fail="Last release behind main",
    ),
    # FR-009 addition (data definition, not in the prototype's 20-check seed):
    Check(
        id="ci_workflow_green", label="CI workflow green on default", group=_G,
        tier=RemediationTier.report, required_capabilities=caps_for_tier(RemediationTier.report),
        evidence_fail="Default-branch CI is failing or not configured",
    ),
]
