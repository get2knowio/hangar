"""Read-path scale: a single-connection overview/scorecard scopes its loads to that
connection (not the whole connection list + entire remediation table), and next_pr_number
asks the database for MAX rather than streaming every row into Python."""

from __future__ import annotations

from hangar.api.deps import load_fleet
from hangar.persistence import repositories as repo


async def _seed_rem(session, conn, repo_id, check, *, pr_number=None) -> None:
    await repo.upsert_remediation(
        session, connection_id=conn, repo_id=repo_id, check_id=check,
        kind="config_pr", state="pr_open", pr_number=pr_number,
    )


async def test_remediation_map_scopes_to_connection(session) -> None:
    await _seed_rem(session, "c1", "r1", "license")
    await _seed_rem(session, "c2", "r2", "license")

    all_map = await repo.remediation_map(session)
    assert {("c1", "r1", "license"), ("c2", "r2", "license")} <= set(all_map)

    scoped = await repo.remediation_map(session, "c1")
    assert set(scoped) == {("c1", "r1", "license")}

    # The "all" sentinel is unscoped (same as no argument).
    assert await repo.remediation_map(session, "all") == all_map


async def test_next_pr_number_uses_sql_max(session) -> None:
    assert await repo.next_pr_number(session) == 143  # empty → seeded 142 + 1

    await _seed_rem(session, "c1", "r1", "license", pr_number=200)
    await _seed_rem(session, "c1", "r2", "license", pr_number=150)
    assert await repo.next_pr_number(session) == 201  # max(200, 150) + 1


async def test_load_fleet_scopes_to_one_connection(client) -> None:
    from hangar.persistence.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        ctx_all = await load_fleet(session, "all")
        assert len(ctx_all.connections) >= 2  # seeded gh-main / gh-labs / gitea

        ctx_one = await load_fleet(session, "gh-main")
        # Only the selected connection is loaded, and every scoped repo belongs to it.
        assert set(ctx_one.connections) == {"gh-main"}
        assert ctx_one.repos and all(r.connection_id == "gh-main" for r in ctx_one.repos)
