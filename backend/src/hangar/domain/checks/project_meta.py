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
        doc_url="https://choosealicense.com/",
    ),
    Check(
        id="readme", label="README present", group=_G,
        tier=RemediationTier.report, required_capabilities=caps_for_tier(RemediationTier.report),
        evidence_fail="README.md missing",
    ),
    Check(
        # Link-tier: Hangar can't synthesize a meaningful description/topics, so it
        # deep-links the operator to repo settings rather than falsely "applying" a no-op.
        id="description", label="Description & topics set", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="Description or topics not set",
    ),
    Check(
        id="templates", label="Issue / PR templates", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        evidence_fail=".github/ISSUE_TEMPLATE absent",
        doc_url="https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests",
    ),
    Check(
        id="contributing", label="CONTRIBUTING present", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        evidence_fail="CONTRIBUTING.md missing",
        doc_url="https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors",
    ),
]
