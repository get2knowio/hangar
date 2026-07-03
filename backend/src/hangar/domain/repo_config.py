"""Parser for the in-repo ``.hangar.json`` config (provider-neutral).

A repo may commit a ``.hangar.json`` at its default branch to declare how Hangar should
treat it. v1 supports one capability: ``ignore`` — suppress named checks for that repo so
they neither pass nor fail, they simply don't participate in the score (Constitution VIII —
suppression is honest and visible, never a fabricated pass).

The file is attacker-influenceable repo content, so parsing is defensive and contained at
the boundary (Constitution III): unknown check ids are dropped, malformed input yields
``None`` (treated as "no config"), and nothing here ever raises into interrogation.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from hangar.domain.checks import CATALOG

logger = logging.getLogger(__name__)


class IgnoreRule(BaseModel):
    check: str
    reason: str = ""


class HangarRepoConfig(BaseModel):
    """Parsed, validated view of a repo's ``.hangar.json`` (FR: per-repo suppression)."""

    version: int = 1
    ignore: list[IgnoreRule] = Field(default_factory=list)

    @classmethod
    def parse(cls, raw: str) -> HangarRepoConfig | None:
        """Parse raw file text; return ``None`` on any malformed/non-conforming input.

        Accepts each ``ignore`` entry as an object ``{"check": id, "reason": ...}`` or a
        bare string shorthand ``"id"``. Unknown check ids are dropped (logged), so a typo or
        a config authored against a newer catalog degrades gracefully rather than crashing.
        """
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("hangar_config.invalid_json")
            return None
        if not isinstance(data, dict):
            logger.warning("hangar_config.not_an_object")
            return None

        rules: list[IgnoreRule] = []
        for entry in data.get("ignore", []) or []:
            if isinstance(entry, str):
                check_id, reason = entry, ""
            elif isinstance(entry, dict) and isinstance(entry.get("check"), str):
                check_id = entry["check"]
                raw_reason = entry.get("reason", "")
                reason = raw_reason if isinstance(raw_reason, str) else ""
            else:
                continue
            if check_id not in CATALOG:
                logger.warning("hangar_config.unknown_check id=%s", check_id)
                continue
            rules.append(IgnoreRule(check=check_id, reason=reason))

        version = data.get("version", 1)
        return cls(version=version if isinstance(version, int) else 1, ignore=rules)

    def suppressions(self) -> dict[str, str]:
        """check_id -> reason (empty string when no reason given). Last rule wins on dupes."""
        return {rule.check: rule.reason for rule in self.ignore}
