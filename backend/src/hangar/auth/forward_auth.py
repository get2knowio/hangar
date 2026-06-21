"""Forward-auth middleware (Constitution III — NON-NEGOTIABLE; FR-027/FR-028/FR-030).

Hangar performs **no app-native login**. In ``forward-auth`` mode the operator identity
arrives in a configurable header (``HANGAR_FORWARD_AUTH_USER_HEADER``, default
``Remote-User``) injected by the reverse proxy. That header is trusted **only** when the
request's immediate peer is inside ``HANGAR_TRUSTED_PROXY_CIDR`` and/or carries the
shared ``HANGAR_TRUSTED_PROXY_SECRET`` — a forged header on a direct request is
rejected (SC-007). An optional ``HANGAR_FORWARD_AUTH_ALLOWED_USER`` pins a single
identity. In ``disabled`` mode every request is admitted and audited as
``HANGAR_OPERATOR``.

The resolved identity is stashed on ``request.state.actor`` for the audit log.
"""

from __future__ import annotations

import ipaddress

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from hangar.config import AccessMode, Settings

log = structlog.get_logger(__name__)

# Paths reachable without authentication (liveness only).
_PUBLIC_PATHS = {"/health", "/api/v1/health", "/docs", "/openapi.json", "/redoc"}


def _peer_trusted(request: Request, settings: Settings) -> bool:
    if settings.trusted_proxy_secret:
        provided = request.headers.get("X-Hangar-Proxy-Secret")
        if provided and provided == settings.trusted_proxy_secret:
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
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in _PUBLIC_PATHS or path.startswith("/assets") or path == "/":
            return await call_next(request)

        mode = self.settings.access_mode

        if mode is AccessMode.disabled:
            request.state.actor = self.settings.operator
            request.state.access_mode = AccessMode.disabled.value
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
