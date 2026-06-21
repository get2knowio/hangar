"""Environment/secret-driven settings and startup validation (FR-027–FR-032).

All operational configuration is supplied via ``HANGAR_*`` environment variables
or secret mounts — there is no in-app configuration UI (Constitution V). The access
mode is *fail-closed*: ``HANGAR_FORWARD_AUTH`` MUST be explicitly set to ``enabled``
or ``disabled`` or the app refuses to start (FR-029, enforced in :func:`validate_startup`).
"""

from __future__ import annotations

import ipaddress
from enum import StrEnum

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AccessMode(StrEnum):
    forward_auth = "forward-auth"
    disabled = "disabled"


class StartupError(RuntimeError):
    """Raised when configuration is unsafe to run (fail-closed, FR-029/FR-030)."""


class Settings(BaseSettings):
    """Typed view over the ``HANGAR_*`` environment.

    Parsing here is permissive (a value may be missing); *enforcement* of the
    non-negotiable security invariants happens in :func:`validate_startup` so that
    the failure is a single, explicit, well-messaged gate (Constitution III).
    """

    model_config = SettingsConfigDict(env_prefix="HANGAR_", env_file=".env", extra="ignore")

    # --- access / forward-auth (FR-027–FR-031) ---
    # Optional at parse time; required-and-validated at startup (fail-closed).
    forward_auth: str | None = Field(default=None, description="enabled|disabled — required")
    forward_auth_user_header: str = Field(default="Remote-User")
    forward_auth_allowed_user: str | None = Field(default=None)
    trusted_proxy_cidr: str | None = Field(default=None)
    trusted_proxy_secret: str | None = Field(default=None)
    allow_public_bind: bool = Field(default=False)
    operator: str = Field(default="local-operator", description="audit actor in disabled mode")

    # --- crypto (FR-032) ---
    secret_key: str | None = Field(default=None, description="Fernet key for credential encryption")

    # --- webhooks (FR-033) ---
    webhook_secret: str | None = Field(
        default=None, description="HMAC secret for inbound provider webhooks; required to accept them"
    )

    # --- persistence ---
    database_url: str = Field(default="sqlite+aiosqlite:///./hangar.db")

    # --- networking / runtime ---
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)
    public_bind: bool = Field(default=False, description="internal alias used by some deploys")

    # --- sync / poller (Constitution VI) ---
    poll_interval_seconds: int = Field(default=300)
    stale_after_seconds: int = Field(default=900)
    seed_demo_data: bool = Field(default=True, description="load prototype fixtures on first boot")

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

    @field_validator("trusted_proxy_cidr")
    @classmethod
    def _validate_cidr(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v:
            for part in v.split(","):
                ipaddress.ip_network(part.strip(), strict=False)
        return v

    @property
    def access_mode(self) -> AccessMode | None:
        if self.forward_auth == "enabled":
            return AccessMode.forward_auth
        if self.forward_auth == "disabled":
            return AccessMode.disabled
        return None

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

    if settings.access_mode is AccessMode.disabled:
        warnings.append(
            "⚠ HANGAR_FORWARD_AUTH=disabled — access control is OFF (network-trust). "
            f"All requests are admitted and audited as operator '{settings.operator}'. "
            "Run this only on a trusted internal network."
        )

    if settings.binds_public and not (settings.allow_public_bind or settings.public_bind):
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
