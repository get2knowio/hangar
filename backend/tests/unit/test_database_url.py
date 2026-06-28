"""Database URL resolution — SQLite default vs discrete HANGAR_POSTGRES_* selection.

Pure settings tests: they assert the *string* the resolver builds and the fail-closed
startup gate; nothing here opens a database connection (no asyncpg needed).
"""

from __future__ import annotations

import pytest

from hangar.config import Settings, StartupError, validate_startup


def test_default_field_is_sqlite() -> None:
    # The field default is SQLite (the test env may override HANGAR_DATABASE_URL).
    assert Settings.model_fields["database_url"].default == "sqlite+aiosqlite:///./hangar.db"


def test_no_postgres_returns_database_url() -> None:
    # With no Postgres host, the resolver passes the database_url field through unchanged.
    settings = Settings()
    assert settings.use_postgres is False
    assert settings.effective_database_url == settings.database_url


def test_postgres_host_builds_url_with_defaults() -> None:
    settings = Settings(postgres_host="db", postgres_password="secret")
    assert settings.use_postgres is True
    assert settings.effective_database_url == (
        "postgresql+asyncpg://hangar:secret@db:5432/hangar"
    )


def test_postgres_honors_custom_port_db_user() -> None:
    settings = Settings(
        postgres_host="pg.internal",
        postgres_port=6543,
        postgres_db="fleet",
        postgres_user="ops",
        postgres_password="pw",
    )
    assert settings.effective_database_url == (
        "postgresql+asyncpg://ops:pw@pg.internal:6543/fleet"
    )


def test_postgres_password_is_url_encoded() -> None:
    settings = Settings(postgres_host="db", postgres_user="a@b", postgres_password="p@ss/wo:rd")
    # @ : / must be percent-encoded so they don't corrupt the netloc.
    assert settings.effective_database_url == (
        "postgresql+asyncpg://a%40b:p%40ss%2Fwo%3Ard@db:5432/hangar"
    )


def test_postgres_sslmode_is_forwarded_verbatim() -> None:
    # asyncpg accepts the libpq mode name directly; forward it (NOT a generic ssl=true,
    # which asyncpg rejects, and which would make verify-full silently not verify).
    require = Settings(postgres_host="db", postgres_password="pw", postgres_sslmode="require")
    assert require.effective_database_url.endswith("/hangar?ssl=require")
    verify = Settings(postgres_host="db", postgres_password="pw", postgres_sslmode="verify-full")
    assert verify.effective_database_url.endswith("/hangar?ssl=verify-full")
    # No sslmode → no query at all.
    plain = Settings(postgres_host="db", postgres_password="pw")
    assert "?" not in plain.effective_database_url


def test_discrete_vars_take_precedence_over_database_url() -> None:
    # The Docker image hardcodes a SQLite HANGAR_DATABASE_URL; discrete Postgres vars must win.
    settings = Settings(
        database_url="sqlite+aiosqlite:////data/hangar.db",
        postgres_host="db",
        postgres_password="pw",
    )
    assert settings.effective_database_url == "postgresql+asyncpg://hangar:pw@db:5432/hangar"


def test_explicit_database_url_used_when_no_postgres_host() -> None:
    url = "postgresql+asyncpg://u:p@elsewhere:5432/other"
    settings = Settings(database_url=url)
    assert settings.use_postgres is False
    assert settings.effective_database_url == url


def test_postgres_host_without_password_raises() -> None:
    settings = Settings(forward_auth="disabled", host="127.0.0.1", postgres_host="db")
    with pytest.raises(StartupError):
        validate_startup(settings)


def test_postgres_fully_configured_warns_not_raises() -> None:
    settings = Settings(
        forward_auth="disabled", host="127.0.0.1", postgres_host="db", postgres_password="pw"
    )
    warnings = validate_startup(settings)
    assert any("Postgres selected" in w for w in warnings)
