"""T084 — /fleet/overview stays well under the 5s budget at ~500 repos (SC-001)."""

from __future__ import annotations

import asyncio
import time

from hangar.persistence.db import get_sessionmaker
from hangar.persistence.models import RepoRow


def _insert_repos(n: int) -> None:
    async def _run() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            for i in range(n):
                session.add(
                    RepoRow(
                        id=f"perf-repo-{i}",
                        connection_id="gh-main",
                        description=f"perf repo {i}",
                        default_branch="main",
                        open_prs=i % 5,
                        dependabot_prs=i % 3,
                        ci_status="fail" if i % 7 == 0 else "pass",
                        alerts={"critical": i % 4 == 0, "high": 0, "moderate": 1, "low": 0},
                        release_pending_days=(i % 30) if i % 2 == 0 else None,
                        fails=["license", "cooldown"] if i % 2 else [],
                        unknowns=["two_fa"] if i % 3 == 0 else [],
                    )
                )
            await session.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


def test_overview_under_5s_with_500_repos(client) -> None:
    # client fixture already ran the lifespan (seed + create_all).
    _insert_repos(500)

    start = time.perf_counter()
    r = client.get("/api/v1/fleet/overview")
    elapsed = time.perf_counter() - start

    assert r.status_code == 200
    body = r.json()
    # 14 seeded + 500 inserted
    assert body["summary"]["repo_count"] == 514
    assert elapsed < 5.0, f"overview took {elapsed:.2f}s (budget 5s)"
