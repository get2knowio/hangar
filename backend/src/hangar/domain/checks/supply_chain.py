"""Supply-chain checks (group: Supply chain)."""

from __future__ import annotations

from hangar.domain.models import Check, RemediationTier

from ._caps import caps_for_tier

_G = "Supply chain"

CHECKS: list[Check] = [
    Check(
        id="dependabot_alerts", label="Dependabot alerts enabled", group=_G,
        tier=RemediationTier.patch, required_capabilities=caps_for_tier(RemediationTier.patch),
        evidence_fail="Alerts disabled",
        doc_url="https://docs.github.com/en/code-security/dependabot/dependabot-alerts",
    ),
    Check(
        # Passes when Dependabot OR Renovate version updates are configured (id kept stable).
        id="dependabot_updates", label="Version updates configured", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        evidence_fail="No Dependabot or Renovate update config",
        doc_url="https://docs.github.com/en/code-security/dependabot/dependabot-version-updates",
    ),
    Check(
        id="cooldown", label="Update cooldown ≥ target", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        has_target=True, default_target=7,
        evidence_fail="No update cooldown configured (Dependabot cooldown / Renovate minimumReleaseAge)",
    ),
    Check(
        id="lockfile", label="Lockfile present", group=_G,
        tier=RemediationTier.report, required_capabilities=caps_for_tier(RemediationTier.report),
        evidence_fail="No lockfile committed",
    ),
    Check(
        id="dep_review", label="Dependency review enabled", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="Dependency-review action absent",
        doc_url="https://github.com/actions/dependency-review-action",
    ),
    # FR-009 addition (data definition, not in the prototype's 20-check seed):
    Check(
        id="actions_pinned_sha", label="Actions pinned to SHA", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="Workflow uses mutable action tags, not pinned SHAs",
        doc_url="https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions",
    ),
]
