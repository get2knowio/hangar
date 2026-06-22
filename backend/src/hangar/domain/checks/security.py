"""Security checks (group: Security)."""

from __future__ import annotations

from hangar.domain.models import Check, RemediationTier

from ._caps import caps_for_tier

_G = "Security"

CHECKS: list[Check] = [
    Check(
        id="security_md", label="SECURITY.md present", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        evidence_fail="SECURITY.md missing",
    ),
    Check(
        id="secret_scanning", label="Secret scanning + push protection", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="Secret scanning off",
    ),
    Check(
        id="code_scanning", label="Code scanning (CodeQL)", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="CodeQL workflow not found",
    ),
    Check(
        id="two_fa", label="Org 2FA required", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="Org 2FA enforcement not on",
    ),
    # FR-009 addition (data definition, not in the prototype's 20-check seed):
    Check(
        id="workflow_permissions", label="Workflow permissions least-privilege", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="GITHUB_TOKEN defaults to write-all; no least-privilege block",
    ),
]
