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
        doc_url="https://docs.github.com/en/code-security/getting-started/adding-a-security-policy-to-your-repository",
    ),
    Check(
        id="secret_scanning", label="Secret scanning + push protection", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="Secret scanning off",
        doc_url="https://docs.github.com/en/code-security/secret-scanning",
    ),
    Check(
        id="code_scanning", label="Code scanning (CodeQL)", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="CodeQL workflow not found",
        doc_url="https://codeql.github.com/",
    ),
    Check(
        id="two_fa", label="Org 2FA required", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="Org 2FA enforcement not on",
        doc_url="https://docs.github.com/en/organizations/keeping-your-organization-secure/managing-two-factor-authentication-for-your-organization",
    ),
    # FR-009 addition (data definition, not in the prototype's 20-check seed):
    Check(
        id="workflow_permissions", label="Workflow permissions least-privilege", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="GITHUB_TOKEN defaults to write-all; no least-privilege block",
        doc_url="https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication",
    ),
]
