"""Fleet endpoints: /fleet/overview and /fleet/scorecard (FR-001–FR-007)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.api.deps import load_fleet, session_dep
from hangar.services.overview import build_overview
from hangar.services.scorecard import build_scorecard
from hangar.services.sync import format_relative

router = APIRouter(tags=["fleet"])


@router.get("/fleet/overview")
async def overview(
    connection: str = Query("all"),
    session: AsyncSession = Depends(session_dep),
) -> dict:
    ctx = await load_fleet(session, connection)
    if connection != "all" and connection in ctx.connections:
        synced = format_relative(ctx.connections[connection].last_sync_at)
    else:
        synced = "2m ago"
    return build_overview(ctx.repos, ctx.connections, ctx.policy, ctx.remediations, synced=synced)


@router.get("/fleet/scorecard")
async def scorecard(
    connection: str = Query("all"),
    failing_only: bool = Query(False),
    session: AsyncSession = Depends(session_dep),
) -> dict:
    ctx = await load_fleet(session, connection)
    return build_scorecard(
        ctx.repos, ctx.connections, ctx.policy, ctx.remediations, failing_only=failing_only
    )
