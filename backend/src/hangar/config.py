"""Environment/secret-driven settings and startup validation (FR-027–FR-032).

All operational configuration is supplied via ``HANGAR_*`` environment variables
or secret mounts — there is no in-app configuration UI (Constitution V). The access
mode is *fail-closed*: an access mode MUST be chosen explicitly or the app refuses to
start (FR-029, enforced in :func:`validate_startup`). The canonical selector is
``HANGAR_ACCESS_MODE`` (``forward-auth`` | ``oidc`` | ``disabled``); when unset, the
legacy ``HANGAR_FORWARD_AUTH`` (``enabled`` | ``disabled``) is honored for backward
compatibility.
"""

from __future__ import annotations

import ipaddress
from enum import StrEnum
from urllib.parse import quote

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AccessMode(StrEnum):
    forward_auth = "forward-auth"
    oidc = "oidc"
    disabled = "disabled"


class StartupError(RuntimeError):
    """Raised when configuration is unsafe to run (fail-closed, FR-029/FR-030)."""


class Settings(BaseSettings):
    """Typed view over the ``HANGAR_*`` environment.

    Parsing here is permissive (a value may be missing); *enforcement* of the
    non-negotiable security invariants happens in :func:`validate_startup` so that
    the failure is a single, explicit, well-messaged gate (Constitution III).
    """

    model_config = SettingsConfigDict(
        env_prefix="HANGAR_", env_file=".env", extra="ignore", populate_by_name=True
    )

    # --- access mode (FR-027–FR-031) ---
    # Canonical selector: forward-auth | oidc | disabled. Optional at parse time;
    # required-and-validated at startup (fail-closed). When unset, the legacy
    # HANGAR_FORWARD_AUTH var below is consulted for backward compatibility.
    access_mode_select: str | None = Field(default=None, alias="HANGAR_ACCESS_MODE")

    # --- forward-auth (legacy gate; still fully supported) ---
    # Optional at parse time; required-and-validated at startup (fail-closed).
    forward_auth: str | None = Field(default=None, description="enabled|disabled — legacy selector")
    forward_auth_user_header: str = Field(default="Remote-User")
    forward_auth_allowed_user: str | None = Field(default=None)
    trusted_proxy_cidr: str | None = Field(default=None)
    trusted_proxy_secret: str | None = Field(default=None)
    allow_public_bind: bool = Field(default=False)
    operator: str = Field(default="local-operator", description="audit actor in disabled mode")

    # --- OIDC (app-native login; HANGAR_OIDC_*) ---
    oidc_issuer: str | None = Field(default=None, description="OIDC issuer base URL (discovery)")
    oidc_client_id: str | None = Field(default=None)
    oidc_client_secret: str | None = Field(default=None)
    # Explicit redirect URI (recommended behind a proxy); else derived from the request.
    oidc_redirect_url: str | None = Field(default=None)
    oidc_scopes: str = Field(default="openid email profile")
    oidc_username_claim: str = Field(default="email", description="claim used as the audit actor")
    # Optional allowlist — admit any authenticated user when both are empty.
    oidc_allowed_users: str | None = Field(default=None, description="CSV of allowed emails/subs")
    oidc_allowed_groups: str | None = Field(default=None, description="CSV of allowed groups")
    oidc_groups_claim: str = Field(default="groups")
    oidc_post_logout_redirect_url: str | None = Field(default=None)

    # --- session cookie (OIDC mode) ---
    session_secret: str | None = Field(default=None, description="signing key; else reuses secret_key")
    session_cookie_name: str = Field(default="hangar_session")
    session_max_age_seconds: int = Field(default=28800)  # 8h
    session_cookie_secure: bool = Field(default=True, description="set false only for local http dev")

    # --- crypto (FR-032) ---
    secret_key: str | None = Field(default=None, description="Fernet key for credential encryption")

    # --- webhooks (FR-033) ---
    webhook_secret: str | None = Field(
        default=None, description="HMAC secret for inbound provider webhooks; required to accept them"
    )

    # --- persistence ---
    # SQLite is the default. The full URL escape hatch is HANGAR_DATABASE_URL; the
    # discrete HANGAR_POSTGRES_* vars below are the ergonomic way to point Hangar at a
    # Postgres instance (and take precedence — see effective_database_url).
    database_url: str = Field(default="sqlite+aiosqlite:///./hangar.db")

    # --- postgres (discrete; optional) ---
    # Setting HANGAR_POSTGRES_HOST switches Hangar to Postgres; the URL is assembled from
    # these. Password has no default (it is a secret); the rest default for the bundled
    # compose `postgres` service so a minimal config is just HOST + PASSWORD.
    postgres_host: str | None = Field(default=None, description="set to enable Postgres")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="hangar")
    postgres_user: str = Field(default="hangar")
    postgres_password: str | None = Field(default=None, description="required when host is set")
    postgres_sslmode: str | None = Field(
        default=None,
        description="libpq sslmode (require/verify-full/…); forwarded to asyncpg's ssl arg",
    )

    # --- networking / runtime ---
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)

    # --- sync / poller (Constitution VI) ---
    poll_interval_seconds: int = Field(default=300)
    stale_after_seconds: int = Field(default=900)
    # Provider-client resilience: a hung request must not stall the whole poll cycle, and a
    # single repo's interrogation fans out many sub-requests — bound the burst so it doesn't
    # trip GitHub's secondary (concurrency) rate limits. Both are plain knobs, not security
    # gates. Rate-limit/5xx retries (honoring Retry-After) are handled inside the adapter.
    github_http_timeout_seconds: float = Field(default=30.0, description="per-request HTTP timeout")
    github_max_concurrency: int = Field(
        default=8, description="max concurrent provider sub-requests per repo interrogation"
    )
    # Off by default — production runs against real provider connections only. Set true
    # (or use the test/offline harness) to load the prototype sample fixtures.
    seed_demo_data: bool = Field(default=False, description="load sample fixtures on first boot")

    # --- static SPA (production single-stack) ---
    static_dir: str | None = Field(default=None, description="built SPA dir to serve at /")

    @field_validator("forward_auth")
    @classmethod
    def _normalize_mode(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if v in {"forward-auth", "forward_auth"}:
            return "enabled"
        return v

    @field_validator("access_mode_select")
    @classmethod
    def _normalize_access_mode(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower().replace("_", "-")
        if v not in {m.value for m in AccessMode}:
            raise ValueError(
                f"HANGAR_ACCESS_MODE must be one of {[m.value for m in AccessMode]}, got '{v}'"
            )
        return v

    @field_validator("trusted_proxy_cidr")
    @classmethod
    def _validate_cidr(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v:
            for part in v.split(","):
                ipaddress.ip_network(part.strip(), strict=False)
        return v

    @property
    def access_mode(self) -> AccessMode | None:
        # Precedence: the canonical HANGAR_ACCESS_MODE wins; else fall back to the legacy
        # HANGAR_FORWARD_AUTH (enabled|disabled) so existing deployments are unchanged.
        if self.access_mode_select:
            return AccessMode(self.access_mode_select)
        if self.forward_auth == "enabled":
            return AccessMode.forward_auth
        if self.forward_auth == "disabled":
            return AccessMode.disabled
        return None  # fail-closed: nothing chosen

    @property
    def oidc_allowed_users_list(self) -> list[str]:
        if not self.oidc_allowed_users:
            return []
        return [u.strip().lower() for u in self.oidc_allowed_users.split(",") if u.strip()]

    @property
    def oidc_allowed_groups_list(self) -> list[str]:
        if not self.oidc_allowed_groups:
            return []
        return [g.strip().lower() for g in self.oidc_allowed_groups.split(",") if g.strip()]

    @property
    def effective_session_secret(self) -> str | None:
        """Cookie-signing key for OIDC sessions — a dedicated secret or the Fernet key."""
        return self.session_secret or self.secret_key

    @property
    def use_postgres(self) -> bool:
        """True when discrete Postgres vars select Postgres over the SQLite/URL default."""
        return bool(self.postgres_host)

    @property
    def effective_database_url(self) -> str:
        """The DB URL the app and Alembic actually use.

        Discrete HANGAR_POSTGRES_* vars win (they are how a Docker deployment opts into
        Postgres, overriding the image's SQLite HANGAR_DATABASE_URL default); otherwise the
        ``database_url`` field (explicit override, else the SQLite default) is returned.
        """
        if not self.use_postgres:
            return self.database_url
        # quote(safe="") so a password/user with @ : / # is URL-safe in the netloc.
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password or "", safe="")
        url = (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
        # asyncpg's `ssl` arg accepts the libpq sslmode names directly
        # (disable/allow/prefer/require/verify-ca/verify-full); forward the mode
        # verbatim so 'verify-full' actually verifies instead of degrading to bare
        # encryption. SQLAlchemy passes ?ssl=<v> straight through to asyncpg, which
        # rejects an unknown value (a hardcoded 'true' would fail at connect time).
        if self.postgres_sslmode:
            url += f"?ssl={quote(self.postgres_sslmode.strip().lower(), safe='')}"
        return url

    @property
    def discovery_url(self) -> str | None:
        if not self.oidc_issuer:
            return None
        return f"{self.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"

    @property
    def trusted_proxy_networks(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        if not self.trusted_proxy_cidr:
            return []
        return [ipaddress.ip_network(p.strip(), strict=False) for p in self.trusted_proxy_cidr.split(",")]

    @property
    def binds_public(self) -> bool:
        """True if the configured bind host is not loopback/internal."""
        try:
            ip = ipaddress.ip_address(self.host)
        except ValueError:
            # A hostname (not a literal IP). Conservatively treat non-localhost names as
            # public so the FR-030 gate fails closed.
            return self.host not in {"localhost", "localhost.localdomain"}
        # 0.0.0.0 / :: bind to *every* interface — that is a public bind regardless of
        # how ``is_private`` classifies the unspecified address on a given Python.
        if ip.is_unspecified:
            return True
        return not (ip.is_loopback or ip.is_private or ip.is_link_local)


def validate_startup(settings: Settings) -> list[str]:
    """Fail-closed startup gate (Constitution III, FR-029/FR-030/FR-031).

    Returns a list of human-readable *warnings* to log. Raises :class:`StartupError`
    when the configuration is unsafe to run. This is the single authoritative gate
    exercised by the auth-mode test suite (T067).
    """
    warnings: list[str] = []

    if settings.access_mode is None:
        raise StartupError(
            "HANGAR_FORWARD_AUTH is not set. Choose an access mode explicitly: "
            "'enabled' (enforce forward-auth at the proxy) or 'disabled' "
            "(network-trust, homelab only). Hangar refuses to start otherwise (fail-closed)."
        )

    if settings.access_mode is AccessMode.forward_auth and not (
        settings.trusted_proxy_networks or settings.trusted_proxy_secret
    ):
        warnings.append(
            "forward-auth is enabled but neither HANGAR_TRUSTED_PROXY_CIDR nor "
            "HANGAR_TRUSTED_PROXY_SECRET is set — the identity header will NOT be "
            "trusted from any source and every request will be rejected."
        )

    if settings.access_mode is AccessMode.oidc:
        missing = [
            name
            for name, value in (
                ("HANGAR_OIDC_ISSUER", settings.oidc_issuer),
                ("HANGAR_OIDC_CLIENT_ID", settings.oidc_client_id),
                ("HANGAR_OIDC_CLIENT_SECRET", settings.oidc_client_secret),
                ("HANGAR_SESSION_SECRET/HANGAR_SECRET_KEY", settings.effective_session_secret),
            )
            if not value
        ]
        if missing:
            raise StartupError(
                "OIDC access mode requires " + ", ".join(missing) + ". Hangar refuses to "
                "start without them (fail-closed)."
            )
        if not settings.session_cookie_secure:
            warnings.append(
                "HANGAR_SESSION_COOKIE_SECURE=false — the session cookie will be sent over "
                "plain HTTP. Use this only for local http:// development."
            )
        if not settings.oidc_redirect_url:
            warnings.append(
                "HANGAR_OIDC_REDIRECT_URL is unset — the redirect_uri will be derived from "
                "request headers. Set it explicitly (or run uvicorn with --proxy-headers) "
                "when Hangar sits behind a TLS-terminating proxy."
            )

    if settings.access_mode is AccessMode.disabled:
        warnings.append(
            "⚠ access mode is 'disabled' — access control is OFF (network-trust). "
            f"All requests are admitted and audited as operator '{settings.operator}'. "
            "Run this only on a trusted internal network."
        )

    # Persistence: discrete Postgres selection is fail-closed on a missing secret.
    if settings.use_postgres:
        if not settings.postgres_password:
            raise StartupError(
                "HANGAR_POSTGRES_HOST is set but HANGAR_POSTGRES_PASSWORD is missing. "
                "Provide the password (or unset HANGAR_POSTGRES_HOST to use SQLite). "
                "Hangar refuses to start otherwise (fail-closed)."
            )
        warnings.append(
            f"Persistence: Postgres selected via HANGAR_POSTGRES_* "
            f"({settings.postgres_user}@{settings.postgres_host}:{settings.postgres_port}/"
            f"{settings.postgres_db})."
        )

    # The ONLY authorized override is HANGAR_ALLOW_PUBLIC_BIND (FR-030, Constitution III).
    if settings.binds_public and not settings.allow_public_bind:
        raise StartupError(
            f"Refusing to bind a public interface ({settings.host}) without "
            "HANGAR_ALLOW_PUBLIC_BIND=1. Bind to an internal/loopback address instead "
            "(FR-030)."
        )

    return warnings


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(settings: Settings) -> None:
    """Override the process settings (used by tests)."""
    global _settings
    _settings = settings
