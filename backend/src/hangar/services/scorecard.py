"""Hygiene scorecard aggregation (FR-005–FR-007; prototype ``scRows``/``scRollup``).

Builds the per-repo × per-check matrix, the fleet compliance roll-up, per-check fail
counts, group spans, and the top-drift chips. Failing-only dimming is applied to cells.
"""

from __future__ import annotations

from hangar.domain.checks import GROUPS
from hangar.domain.models import FindingStatus, Policy, ProviderConnection, Repo
from hangar.domain.policy import (
    RemediationMap,
    effective_status,
    enabled_checks,
    hygiene,
)


def _badge_before_colon(label: str) -> str:
    return label.split(":")[0]


def build_scorecard(
    repos: list[Repo],
    connections: dict[str, ProviderConnection],
    policy: Policy,
    remediations: RemediationMap,
    *,
    failing_only: bool = False,
) -> dict:
    checks = enabled_checks(policy)
    compliance = round(sum(hygiene(r, policy, remediations) for r in repos) / len(repos)) if repos else 100
    clear = sum(1 for r in repos if hygiene(r, policy, remediations) >= 85)

    # group spans (only groups with at least one enabled check)
    groups = []
    for g in GROUPS:
        n = sum(1 for c in checks if c.group == g)
        if n:
            groups.append({"label": g, "span": n})

    # per-check fail counts (across the visible fleet)
    check_meta = []
    for c in checks:
        fails = sum(1 for r in repos if effective_status(r, c.id, remediations) is not FindingStatus.passing)
        check_meta.append({"id": c.id, "label": c.label, "fail_count": fails})

    rows = []
    for r in repos:
        cells = []
        for c in checks:
            st = effective_status(r, c.id, remediations)
            cells.append(st.value)
        conn = connections.get(r.connection_id)
        rows.append({
            "repo_id": r.id,
            "hygiene_pct": hygiene(r, policy, remediations),
            "connection_badge": _badge_before_colon(conn.label) if conn else r.connection_id,
            "cells": cells,
        })

    rollup = []
    for c in checks:
        fails = sum(1 for r in repos if effective_status(r, c.id, remediations) is FindingStatus.fail)
        if fails:
            label = c.label.lower().replace(" present", "").replace(" enabled", "")
            rollup.append({"label": label, "count": fails})
    rollup.sort(key=lambda x: x["count"], reverse=True)
    rollup = rollup[:4]

    return {
        "compliance_pct": compliance,
        "clear_count": clear,
        "repo_count": len(repos),
        "failing_only": failing_only,
        "groups": groups,
        "checks": check_meta,
        "rows": rows,
        "rollup": rollup,
    }
