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
)


def _badge_before_colon(label: str) -> str:
    # The dense scorecard column shows the provider prefix ("gh"); the overview table,
    # which has more room, shows the org ("get2knowio"). This asymmetry is intentional
    # and matches the prototype — do not "unify" them.
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
    n_checks = len(checks)

    # Single O(repos × checks) pass: build the status matrix once, then derive every
    # roll-up (compliance, clear, per-check counts, rows, top-drift) from it — instead
    # of re-running effective_status/hygiene ~5× per cell.
    matrix: dict[str, list[FindingStatus]] = {}
    hyg: dict[str, int] = {}
    for r in repos:
        statuses = [effective_status(r, c.id, remediations) for c in checks]
        matrix[r.id] = statuses
        passing = sum(1 for s in statuses if s is FindingStatus.passing)
        hyg[r.id] = round(passing / n_checks * 100) if n_checks else 100

    compliance = round(sum(hyg.values()) / len(repos)) if repos else 100
    clear = sum(1 for v in hyg.values() if v >= 85)

    groups = []
    for g in GROUPS:
        n = sum(1 for c in checks if c.group == g)
        if n:
            groups.append({"label": g, "span": n})

    check_meta = []
    rollup: list[dict[str, str | int]] = []
    for i, c in enumerate(checks):
        # fail_count is *failures only* — `unknown` (undeterminable) and pending/working
        # (in-flight remediations) must not be conflated with a fail (honest state).
        fails = sum(1 for r in repos if matrix[r.id][i] is FindingStatus.fail)
        check_meta.append({"id": c.id, "label": c.label, "fail_count": fails})
        if fails:
            label = c.label.lower().replace(" present", "").replace(" enabled", "")
            rollup.append({"label": label, "count": fails})
    rollup.sort(key=lambda x: int(x["count"]), reverse=True)
    rollup = rollup[:4]

    rows = []
    for r in repos:
        conn = connections.get(r.connection_id)
        rows.append({
            "repo_id": r.id,
            "hygiene_pct": hyg[r.id],
            "connection_badge": _badge_before_colon(conn.label) if conn else r.connection_id,
            "cells": [s.value for s in matrix[r.id]],
        })

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
