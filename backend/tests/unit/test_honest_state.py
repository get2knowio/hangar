"""Honest-state regressions (Constitution VIII): the relative-time humanizer must not
mask a future timestamp as a fresh 'just now', and the demo seed derives real, aging
timestamps from its fixture offsets rather than freezing display strings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hangar.persistence.seed import _ago
from hangar.services.sync import format_relative


def test_format_relative_past_buckets() -> None:
    now = datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC)
    assert format_relative(now - timedelta(seconds=10), now=now) == "just now"
    assert format_relative(now - timedelta(minutes=3), now=now) == "3m ago"
    assert format_relative(now - timedelta(hours=2), now=now) == "2h ago"
    assert format_relative(now - timedelta(days=1, hours=2), now=now) == "yesterday"
    assert format_relative(now - timedelta(days=4), now=now) == "4d ago"
    assert format_relative(None, now=now) == "never"


def test_format_relative_tolerates_subminute_future_skew() -> None:
    # A just-written timestamp can read a few ms/s ahead of `now` — benign, still "just now".
    now = datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC)
    assert format_relative(now + timedelta(seconds=5), now=now) == "just now"


def test_format_relative_surfaces_large_future_timestamp() -> None:
    # A meaningfully-future timestamp is anomalous (clock skew / bad data) and must NOT be
    # masked as a fresh "just now".
    now = datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC)
    assert format_relative(now + timedelta(hours=1), now=now) == "in the future"


def test_ago_parses_fixture_offsets() -> None:
    assert _ago("2m ago") == timedelta(minutes=2)
    assert _ago("12m ago") == timedelta(minutes=12)
    assert _ago("1h ago") == timedelta(hours=1)
    assert _ago("3d ago") == timedelta(days=3)
    assert _ago("yesterday") == timedelta(hours=26)
    assert _ago("garbage") == timedelta()
