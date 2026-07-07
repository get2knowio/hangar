"""Catalog & policy endpoints (FR-008, FR-009, FR-019, FR-020).

The catalog is data: toggling a check or changing a target mutates the single fleet-wide
policy and the scorecard recomputes — no dashboard code changes (Constitution IV, SC-005).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.api.deps import session_dep
from hangar.domain.checks import GROUPS, all_checks
from hangar.domain.models import FindingStatus, PolicyEntry, tier_label
from hangar.domain.policy import effective_status
from hangar.persistence import repositories as repo_store

router = APIRouter(tags=["catalog"])


@router.get("/catalog")
async def catalog(session: AsyncSession = Depends(session_dep)) -> dict:
    policy = await repo_store.get_policy(session)
    repos = await repo_store.list_repos(session)
    remediations = await repo_store.remediation_map(session)
    total_repos = len(repos)

    groups = []
    enabled_count = 0
    for g in GROUPS:
        checks = []
        for c in (x for x in all_checks() if x.group == g):
            enabled = policy.is_enabled(c.id)
            enabled_count += 1 if enabled else 0
            passes = sum(
                1 for r in repos if effective_status(r, c.id, remediations) is FindingStatus.passing
            )
            checks.append({
                "id": c.id,
                "label": c.label,
                "tier": c.tier.value,
                "tier_label": tier_label(c.tier),
                "enabled": enabled,
                "has_target": c.has_target,
                "target": policy.target(c.id),
                "pass_count": passes,
                "repo_count": total_repos,
                "doc_url": c.doc_url,
            })
        groups.append({"group": g, "checks": checks})

    return {
        "enabled_count": enabled_count,
        "total_count": len(all_checks()),
        "groups": groups,
    }


@router.get("/policy")
async def get_policy(session: AsyncSession = Depends(session_dep)) -> dict:
    policy = await repo_store.get_policy(session)
    return policy.model_dump()


class PolicyPatch(BaseModel):
    check_id: str
    enabled: bool | None = None
    params: dict | None = None


@router.patch("/policy")
async def patch_policy(
    patch: PolicyPatch, session: AsyncSession = Depends(session_dep)
) -> dict:
    policy = await repo_store.get_policy(session)
    entry = policy.entry(patch.check_id)
    if entry is None:
        entry = PolicyEntry(check_id=patch.check_id)
        policy.entries.append(entry)
    if patch.enabled is not None:
        entry.enabled = patch.enabled
    if patch.params is not None:
        entry.params = {**entry.params, **patch.params}
    await repo_store.save_policy(session, policy)
    return policy.model_dump()
