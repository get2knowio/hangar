"""Shared capability-requirement helper for check definitions.

Kept in its own module so the per-group check modules can import it without a circular
dependency on the package ``__init__`` (which imports those modules).
"""

from __future__ import annotations

from hangar.domain.models import Capability, RemediationTier


def caps_for_tier(tier: RemediationTier) -> dict[RemediationTier, list[Capability]]:
    """Standard capability requirements for a check whose native tier is ``tier``.

    Every check can always degrade: link needs deep-link, report needs nothing. Write
    tiers (patch/pr) require the corresponding write capability and otherwise collapse
    to deep-link then report (FR-010, FR-018).
    """
    reqs: dict[RemediationTier, list[Capability]] = {
        RemediationTier.report: [],
        RemediationTier.link: [Capability.deep_link],
    }
    if tier is RemediationTier.patch:
        reqs[RemediationTier.patch] = [Capability.write_settings]
    elif tier is RemediationTier.pr:
        reqs[RemediationTier.pr] = [Capability.open_pull_request, Capability.read_files]
    return reqs
