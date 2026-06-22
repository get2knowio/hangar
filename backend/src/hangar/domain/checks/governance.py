"""Governance checks (group: Governance)."""

from __future__ import annotations

from hangar.domain.models import Check, RemediationTier

from ._caps import caps_for_tier

_G = "Governance"

CHECKS: list[Check] = [
    Check(
        id="branch_protection", label="Branch protection on default", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="No ruleset on `main`",
    ),
    Check(
        id="codeowners", label="CODEOWNERS present", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        evidence_fail="CODEOWNERS missing",
    ),
    Check(
        id="default_branch", label="Default branch = main", group=_G,
        tier=RemediationTier.report, required_capabilities=caps_for_tier(RemediationTier.report),
        evidence_fail="Default branch not main",
    ),
]
