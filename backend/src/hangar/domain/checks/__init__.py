"""The declarative check catalog (Constitution IV, FR-008/FR-009).

A *check* is pure data: an id, a human label, a group, a native remediation tier, the
capabilities each tier requires, and the evidence shown when it fails. Adding or
changing a check is a data edit here — never dashboard code. The catalog is the full
FR-009 set of **23**: the prototype's 20 seed checks plus three added as definitions
(CI-workflow-green, Actions-pinned-to-SHA, workflow-permissions-least-privilege).

Detection (which repos pass/fail/unknown) is performed by the provider adapters, which
populate ``Repo.fails`` / ``Repo.unknowns`` from read-only interrogation; a check that
cannot be determined for lack of scope yields ``unknown``, never a false pass/fail
(research.md §11).
"""

from __future__ import annotations

from hangar.domain.models import Check

from ._caps import caps_for_tier
from .governance import CHECKS as _governance
from .project_meta import CHECKS as _project_meta
from .release import CHECKS as _release
from .security import CHECKS as _security
from .supply_chain import CHECKS as _supply_chain

# Display order mirrors the prototype's GROUPS.
GROUPS: list[str] = ["Supply chain", "Release", "Governance", "Security", "Project meta"]

_ALL: list[Check] = [*_supply_chain, *_release, *_governance, *_security, *_project_meta]

CATALOG: dict[str, Check] = {c.id: c for c in _ALL}


def all_checks() -> list[Check]:
    """Catalog in canonical group/definition order."""
    ordered: list[Check] = []
    for group in GROUPS:
        ordered.extend(c for c in _ALL if c.group == group)
    return ordered


__all__ = ["CATALOG", "GROUPS", "all_checks", "caps_for_tier"]
