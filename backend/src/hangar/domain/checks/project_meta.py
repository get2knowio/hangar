"""Project-metadata checks (group: Project meta)."""

from __future__ import annotations

from hangar.domain.models import Check, RemediationTier

from ._caps import caps_for_tier

_G = "Project meta"

CHECKS: list[Check] = [
    Check(
        id="license", label="LICENSE present", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        evidence_fail="No LICENSE file at repo root",
    ),
    Check(
        id="readme", label="README present", group=_G,
        tier=RemediationTier.report, required_capabilities=caps_for_tier(RemediationTier.report),
        evidence_fail="README.md missing",
    ),
    Check(
        id="description", label="Description & topics set", group=_G,
        tier=RemediationTier.patch, required_capabilities=caps_for_tier(RemediationTier.patch),
        evidence_fail="Repo description & topics empty",
    ),
    Check(
        id="templates", label="Issue / PR templates", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        evidence_fail=".github/ISSUE_TEMPLATE absent",
    ),
]
