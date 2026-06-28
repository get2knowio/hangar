"""Access-control middleware (Constitution III — NON-NEGOTIABLE; FR-027/FR-028/FR-030).

Dispatches on the configured access mode and stashes the resolved identity on
``request.state.actor`` for the audit log:

- ``forward-auth``: the operator identity arrives in a configurable header
  (``HANGAR_FORWARD_AUTH_USER_HEADER``, default ``Remote-User``) injected by the reverse
  proxy. That header is trusted **only** when the request's immediate peer is inside
  ``HANGAR_TRUSTED_PROXY_CIDR`` and/or carries the shared ``HANGAR_TRUSTED_PROXY_SECRET`` — a
  forged header on a direct request is rejected (SC-007). An optional
  ``HANGAR_FORWARD_AUTH_ALLOWED_USER`` pins a single identity.
- ``oidc``: app-native login. The identity lives in a signed session cookie established by
  the ``/auth/callback`` after a validated OIDC sign-in; no valid session yields 401.
- ``disabled``: every request is admitted and audited as ``HANGAR_OPERATOR``.
"""

from __future__ import annotations

import hmac
import ipaddress
import time

import structlog
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from hangar.config import AccessMode, Settings

log = structlog.get_logger(__name__)

# Paths reachable without a proxy identity.
#  - liveness probes (no data)
#  - inbound provider webhooks: authenticated by their HMAC signature, not the proxy
#    identity, since providers POST directly rather than through the forward-auth proxy.
_PUBLIC_PATHS = {"/health", "/api/v1/health", "/docs", "/openapi.json", "/redoc"}
#  - /auth/*: the OIDC browser-redirect + pre-login probe endpoints, reachable before a
#    session exists (the flow that establishes the session). They guard themselves.
_PUBLIC_PREFIXES = ("/api/v1/webhooks/", "/auth/")


def _peer_trusted(request: Request, settings: Settings) -> bool:
    if settings.trusted_proxy_secret:
        provided = request.headers.get("X-Hangar-Proxy-Secret")
        # Constant-time compare — this secret is the bearer credential that lets a peer
        # inject an identity header; a plain == would leak it via response timing.
        if provided and hmac.compare_digest(provided, settings.trusted_proxy_secret):
            return True
    nets = settings.trusted_proxy_networks
    if not nets:
        return False
    client = request.client.host if request.client else None
    if not client:
        return False
    try:
        ip = ipaddress.ip_address(client)
    except ValueError:
        return False
    return any(ip in net for net in nets)


class ForwardAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if (
            path in _PUBLIC_PATHS
            or path == "/"
            or path.startswith("/assets/")
            or path.startswith(_PUBLIC_PREFIXES)
        ):
            return await call_next(request)

        mode = self.settings.access_mode

        if mode is AccessMode.disabled:
            request.state.actor = self.settings.operator
            request.state.access_mode = AccessMode.disabled.value
            return await call_next(request)

        if mode is AccessMode.oidc:
            # App-native login: the identity lives in the signed session cookie (set by the
            # /auth/callback after a validated OIDC login). No valid session ⇒ 401, and the
            # SPA renders its login screen. request.session is provided by SessionMiddleware.
            session = request.session
            actor = session.get("actor")
            exp = session.get("exp")
            if not actor or (exp is not None and time.time() > float(exp)):
                return JSONResponse({"detail": "authentication required"}, status_code=401)
            request.state.actor = actor
            request.state.access_mode = AccessMode.oidc.value
            return await call_next(request)

        # forward-auth: trust the identity header only from the proxy.
        if not _peer_trusted(request, self.settings):
            log.warning("auth.untrusted_peer", path=path,
                        peer=request.client.host if request.client else None)
            return JSONResponse(
                {"detail": "identity header not trusted from this source"}, status_code=403
            )

        identity = request.headers.get(self.settings.forward_auth_user_header)
        if not identity:
            return JSONResponse({"detail": "missing forward-auth identity header"}, status_code=401)

        allowed = self.settings.forward_auth_allowed_user
        if allowed and identity != allowed:
            return JSONResponse({"detail": "identity not permitted"}, status_code=403)

        request.state.actor = identity
        request.state.access_mode = AccessMode.forward_auth.value
        return await call_next(request)


def current_actor(request: Request) -> str:
    """FastAPI helper: the resolved actor for audit (always non-null past middleware)."""
    return getattr(request.state, "actor", None) or "unknown"
