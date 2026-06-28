"""OIDC browser-redirect endpoints (``/auth/*``).

These are app-level routes (NOT under ``/api/v1``), registered before the SPA catch-all and
exempt from the auth middleware so the unauthenticated browser can start the login flow. The
flow is Authorization-Code + PKCE; on success the resolved identity is written to the signed
session cookie (Starlette ``SessionMiddleware``) and the browser is sent back to the SPA.
"""

from __future__ import annotations

import time

import structlog
from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from hangar.api.deps import settings_dep
from hangar.auth.oidc import get_oauth, is_admitted, resolve_identity
from hangar.config import AccessMode, Settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _redirect_uri(request: Request, settings: Settings) -> str:
    """The OIDC redirect URI: explicit config wins; else derive from the request.

    Behind a TLS-terminating proxy the internal scheme/host differ from the public ones, so
    ``HANGAR_OIDC_REDIRECT_URL`` is recommended; the derived form honors forwarded headers
    when uvicorn runs with ``--proxy-headers``.
    """
    if settings.oidc_redirect_url:
        return settings.oidc_redirect_url
    return str(request.url_for("auth_callback"))


@router.get("/info")
async def auth_info(request: Request, settings: Settings = Depends(settings_dep)) -> dict:
    """Public pre-login probe so the SPA can decide whether to render the login screen.

    Kept separate from ``/me`` on purpose: ``/me`` stays behind the auth middleware (exempting
    it would let a forged identity header reach it in forward-auth mode).
    """
    mode = settings.access_mode
    if mode is AccessMode.oidc:
        authenticated = bool(request.session.get("actor"))
        actor = request.session.get("actor")
    else:
        # forward-auth / disabled resolve identity at the proxy/middleware, not via a login UI.
        authenticated = True
        actor = None
    return {
        "mode": mode.value if mode else "disabled",
        "authenticated": authenticated,
        "actor": actor,
        "login_url": "/auth/login",
        "logout_url": "/auth/logout",
    }


@router.get("/login", include_in_schema=False)
async def auth_login(request: Request, settings: Settings = Depends(settings_dep)) -> Response:
    if settings.access_mode is not AccessMode.oidc:
        return JSONResponse({"detail": "OIDC is not the active access mode"}, status_code=404)
    oauth = get_oauth(settings)
    # Authlib stashes state + nonce + PKCE verifier in request.session and 302s to the IdP.
    return await oauth.hangar.authorize_redirect(request, _redirect_uri(request, settings))


@router.get("/callback", name="auth_callback", include_in_schema=False)
async def auth_callback(request: Request, settings: Settings = Depends(settings_dep)) -> Response:
    if settings.access_mode is not AccessMode.oidc:
        return JSONResponse({"detail": "OIDC is not the active access mode"}, status_code=404)
    oauth = get_oauth(settings)
    try:
        # Validates state (CSRF), exchanges the code, and validates the ID token
        # (signature via JWKS, iss/aud/exp, and the nonce) — all in Authlib.
        token = await oauth.hangar.authorize_access_token(request)
    except OAuthError as exc:
        log.warning("auth.oidc_callback_failed", error=str(exc))
        return JSONResponse({"detail": "authentication failed"}, status_code=401)

    claims = token.get("userinfo") or {}
    if not claims:
        return JSONResponse({"detail": "no identity claims in token"}, status_code=401)
    if not is_admitted(claims, settings):
        request.session.clear()
        log.warning("auth.oidc_not_permitted", sub=claims.get("sub"))
        return JSONResponse({"detail": "user not permitted"}, status_code=403)

    request.session.clear()  # drop the transient OAuth state
    request.session["actor"] = resolve_identity(claims, settings)
    request.session["exp"] = int(time.time()) + settings.session_max_age_seconds
    if claims.get("sub"):
        request.session["sub"] = str(claims["sub"])
    log.info("auth.oidc_login", actor=request.session["actor"])
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
async def auth_logout(request: Request, settings: Settings = Depends(settings_dep)) -> Response:
    request.session.clear()
    # Best-effort RP-initiated logout at the IdP when configured and advertised.
    if settings.access_mode is AccessMode.oidc and settings.oidc_post_logout_redirect_url:
        try:
            meta = await get_oauth(settings).hangar.load_server_metadata()
            end = meta.get("end_session_endpoint")
        except Exception:  # noqa: BLE001 — logout must still succeed locally if the IdP is down
            end = None
        if end:
            sep = "&" if "?" in end else "?"
            return RedirectResponse(
                f"{end}{sep}post_logout_redirect_uri={settings.oidc_post_logout_redirect_url}",
                status_code=303,
            )
    return JSONResponse({"ok": True})
