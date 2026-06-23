"""Shared API dependencies and fleet-context loading."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from hangar.auth.forward_auth import current_actor
from hangar.config import Settings, get_settings
from hangar.domain.models import Policy, ProviderConnection, Repo
from hangar.domain.policy import RemediationMap
from hangar.persistence import repositories as repo_store
from hangar.persistence.db import get_session


async def session_dep() -> AsyncGenerator[AsyncSession, None]:  # pragma: no cover - thin wrapper
    async for s in get_session():
        yield s


def settings_dep() -> Settings:
    return get_settings()


def actor_dep(request: Request) -> str:
    return current_actor(request)


@dataclass(slots=True)
class FleetContext:
    repos: list[Repo]
    connections: dict[str, ProviderConnection]
    policy: Policy
    remediations: RemediationMap


async def load_fleet(session: AsyncSession, connection: str = "all") -> FleetContext:
    """Fleet-wide context for the overview/scorecard endpoints. The repo-detail path does
    NOT use this — it loads only its one connection + that repo's remediation overlay."""
    repos = await repo_store.list_repos(session, connection)
    conns = {c.id: c for c in await repo_store.list_connections(session)}
    policy = await repo_store.get_policy(session)
    remediations = await repo_store.remediation_map(session)
    return FleetContext(repos, conns, policy, remediations)


SessionDep = Depends(session_dep)
SettingsDep = Depends(settings_dep)
ActorDep = Depends(actor_dep)
