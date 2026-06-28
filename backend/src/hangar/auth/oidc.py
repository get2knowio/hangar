"""OIDC client wiring (Constitution III — app-native login, fail-closed).

Hangar acts as a **confidential OIDC client** in ``oidc`` access mode: it runs the
Authorization-Code-with-PKCE flow against the operator's own identity provider (Authentik,
Keycloak, …) and establishes a signed session cookie. All token/JWKS/ID-token validation is
delegated to **Authlib** — Hangar never hand-rolls JWT or JWKS crypto. Using a *provider*
(GitHub/Gitea) as the identity gate remains forbidden; the IdP here is the homelab's SSO, the
same one a forward-auth proxy would delegate to.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from authlib.integrations.starlette_client import OAuth

if TYPE_CHECKING:
    from hangar.config import Settings

# The single registered OIDC client name (Authlib addresses clients by name, e.g. oauth.hangar).
CLIENT_NAME = "hangar"


def build_oauth(settings: Settings) -> OAuth:
    """Construct an Authlib ``OAuth`` registry with one registered OIDC client.

    Discovery (``server_metadata_url``), JWKS fetch/cache, PKCE, and full ID-token validation
    (signature, ``iss``/``aud``/``exp``/``nonce``) are all handled by Authlib on top of the
    already-present httpx.
    """
    oauth = OAuth()
    oauth.register(
        name=CLIENT_NAME,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=settings.discovery_url,
        client_kwargs={
            "scope": settings.oidc_scopes,
            "code_challenge_method": "S256",  # PKCE
        },
    )
    return oauth


_oauth: OAuth | None = None


def get_oauth(settings: Settings) -> OAuth:
    """Process-lifetime singleton OAuth registry (discovery/JWKS are cached within it)."""
    global _oauth
    if _oauth is None:
        _oauth = build_oauth(settings)
    return _oauth


def reset_oauth() -> None:
    """Drop the cached registry (used by tests that reconfigure OIDC settings)."""
    global _oauth
    _oauth = None


def resolve_identity(claims: Mapping[str, Any], settings: Settings) -> str:
    """The audit actor string from validated ID-token claims (username claim → ``sub``)."""
    return str(claims.get(settings.oidc_username_claim) or claims.get("sub") or "unknown")


def is_admitted(claims: Mapping[str, Any], settings: Settings) -> bool:
    """Whether these claims pass the optional allowlist.

    With no allowlist configured (neither users nor groups), any IdP-authenticated user is
    admitted — access is then gated entirely by the IdP's own app assignment. When an
    allowlist is set, the user must match by email/sub OR have an allowed group claim.
    """
    users = settings.oidc_allowed_users_list
    groups = settings.oidc_allowed_groups_list
    if not users and not groups:
        return True
    if users:
        ident = resolve_identity(claims, settings).lower()
        sub = str(claims.get("sub", "")).lower()
        if ident in users or (sub and sub in users):
            return True
    if groups:
        claim_groups = {str(g).lower() for g in (claims.get(settings.oidc_groups_claim) or [])}
        if claim_groups & set(groups):
            return True
    return False
