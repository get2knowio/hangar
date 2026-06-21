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
    ),
    Check(
        id="dependabot_updates", label="Version updates configured", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        evidence_fail="dependabot.yml has no updates block",
    ),
    Check(
        id="cooldown", label="Update cooldown ≥ target", group=_G,
        tier=RemediationTier.pr, required_capabilities=caps_for_tier(RemediationTier.pr),
        has_target=True, default_target=7,
        evidence_fail="No cooldown block in dependabot.yml",
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
    ),
    # FR-009 addition (data definition, not in the prototype's 20-check seed):
    Check(
        id="actions_pinned_sha", label="Actions pinned to SHA", group=_G,
        tier=RemediationTier.link, required_capabilities=caps_for_tier(RemediationTier.link),
        evidence_fail="Workflow uses mutable action tags, not pinned SHAs",
    ),
]
