"""One-click "Connect with GitHub" — App **manifest + install** flow (#25).

Three browser-redirect GETs under ``/api/v1/providers/github/app`` that turn "create a
GitHub App + install it" into two clicks, capturing the App credentials and the
``installation_id`` automatically (no copy-paste):

1. ``/new``      — POST a generated **manifest** to ``{host}/settings/apps/new`` (or, when an
   App already exists for this host, jump straight to install).
2. ``/created``  — the manifest ``redirect_url``: exchange the one-time ``code`` for the App's
   credentials, persist the per-host registration, then redirect to GitHub's **install** page.
3. ``/installed``— the App ``setup_url``: resolve the installation's owner + repo selection and
   create the connection.

Multi-host: every GitHub URL is derived from the connection's ``base_url`` by the adapter
helpers, so github.com, GHEC (incl. data-residency ``*.ghe.com``) and GHES all work.

These routes sit **behind** the access-control middleware (the operator is already logged
into Hangar). CSRF is a single-use ``state`` carried in the signed session cookie — the same
pattern the OIDC callback relies on (Constitution III, fail-closed). All App secrets are
Fernet-encrypted at rest (FR-032); webhooks ship **off** (``hook_attributes.active=false``).
"""

from __future__ import annotations

import json
import secrets
from html import escape as html_escape
from urllib.parse import urlsplit

import httpx
import structlog
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from hangar.api.deps import session_dep, settings_dep
from hangar.config import Settings
from hangar.persistence import repositories as repo_store
from hangar.persistence.crypto import decrypt, encrypt
from hangar.persistence.models import ConnectionRow
from hangar.persistence.repositories import get_app_registration, upsert_app_registration
from hangar.providers.github.adapter import (
    github_api_base,
    github_app_delete_url,
    github_install_prefix,
    github_web_base,
)
from hangar.services.audit import record_correction
from hangar.services.connections import add_connection, remove_connection

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/providers/github/app", tags=["providers"])

# Transient flow state lives under this session key (signed cookie via SessionMiddleware).
_SESSION_KEY = "gh_app_flow"


def _instance_base_url(request: Request, settings: Settings) -> str:
    """The instance's browser-visible base URL for the manifest callback URLs.

    Explicit ``HANGAR_BASE_URL`` wins (recommended behind a proxy); else derive from the
    request (honors forwarded headers when uvicorn runs with ``--proxy-headers``). LAN/VPN
    URLs are valid — these are browser redirects; GitHub never connects inbound.
    """
    if settings.base_url:
        return settings.base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _manifest_permissions(writable: bool) -> dict[str, str]:
    """GitHub App permissions for the checks Hangar evaluates (provider-owned mapping).

    Reads cover the 23-check catalog (repo settings, security alerts, org 2FA); write tiers
    (contents/pull_requests) are requested ONLY for a writable connection so Hangar can open
    fix PRs — least-privilege otherwise (FR-026).
    """
    perms = {
        "metadata": "read",
        "administration": "read",  # branch protection / repo settings reads
        "security_events": "read",  # code-scanning alerts
        "vulnerability_alerts": "read",  # Dependabot alerts
        "members": "read",  # org 2FA-enforcement check
    }
    if writable:
        perms["contents"] = "write"  # commit remediation files on a branch
        perms["pull_requests"] = "write"  # open the fix PR
    return perms


def _build_manifest(instance_base: str, writable: bool, public: bool = False) -> dict:
    """The GitHub App manifest. Webhooks are off for the MVP (no inbound dependency).

    ``public`` (HANGAR_GITHUB_APP_PUBLIC) controls installability: a private App can be
    installed only on the owner's account, so leaving it false confines Hangar to the
    operator's personal repos; true lets the operator install it on their orgs too.
    """
    host = urlsplit(instance_base).netloc or "hangar"
    return {
        "name": f"Hangar ({host})",
        "url": instance_base,
        "redirect_url": f"{instance_base}/api/v1/providers/github/app/created",
        "setup_url": f"{instance_base}/api/v1/providers/github/app/installed",
        "setup_on_update": True,
        "public": public,
        "default_permissions": _manifest_permissions(writable),
        "default_events": [],
        "hook_attributes": {
            # Required field even when inactive; webhooks are deferred (#25 non-goal).
            "url": f"{instance_base}/api/v1/webhooks/github-app",
            "active": False,
        },
    }


def _autosubmit_form(action: str, manifest: dict) -> str:
    """A tiny auto-submitting form that POSTs the manifest to GitHub (browser-driven)."""
    payload = html_escape(json.dumps(manifest), quote=True)
    return (
        "<!doctype html><html><head><title>Connecting to GitHub…</title></head>"
        '<body onload="document.forms[0].submit()">'
        f'<form method="post" action="{html_escape(action, quote=True)}">'
        f'<input type="hidden" name="manifest" value="{payload}">'
        "<noscript><button type=\"submit\">Continue to GitHub</button></noscript>"
        "</form></body></html>"
    )


def _install_url(web_base: str, slug: str, state: str) -> str:
    return f"{web_base}{github_install_prefix(web_base)}/{slug}/installations/new?state={state}"


def _reject(reason: str, status: int = 400) -> JSONResponse:
    """A flow rejection the SPA never reaches via redirect (e.g. CSRF) — fail closed."""
    return JSONResponse({"detail": reason}, status_code=status)


def _spa_error(reason: str) -> RedirectResponse:
    """Send the browser back to the SPA with an error flag for a user-facing toast."""
    return RedirectResponse(f"/providers?connect_error={reason}", status_code=303)


@router.get("/new", include_in_schema=False)
async def app_new(
    request: Request,
    base_url: str = Query("https://github.com"),
    writable: bool = Query(True),
    session: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> Response:
    """Start the flow: provision (or reuse) the App for ``base_url`` and head to GitHub."""
    web = github_web_base(base_url)
    state = secrets.token_urlsafe(32)

    # Reuse an App already provisioned for this host — skip creation, go straight to install.
    existing = await get_app_registration(session, web)
    if existing is not None:
        request.session[_SESSION_KEY] = {"state": state, "base_url": web, "writable": writable}
        return RedirectResponse(_install_url(web, existing.slug, state), status_code=303)

    request.session[_SESSION_KEY] = {"state": state, "base_url": web, "writable": writable}
    manifest = _build_manifest(
        _instance_base_url(request, settings), writable, public=settings.github_app_public
    )
    action = f"{web}/settings/apps/new?state={state}"
    return HTMLResponse(_autosubmit_form(action, manifest))


@router.get("/created", include_in_schema=False)
async def app_created(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> Response:
    """Manifest ``redirect_url``: exchange the code for App credentials; persist; go install."""
    saved = request.session.get(_SESSION_KEY) or {}
    if not saved.get("state") or not secrets.compare_digest(str(saved["state"]), state):
        return _reject("state mismatch")
    web = str(saved["base_url"])
    api = github_api_base(web)

    try:
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                f"{api}/app-manifests/{code}/conversions",
                headers={"Accept": "application/vnd.github+json"},
            )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — surface to the operator, log cause server-side
        log.warning("github_app.conversion_failed", base_url=web, error=str(exc))
        return _spa_error("conversion_failed")

    app_id = str(data["id"])
    slug = str(data["slug"])
    await upsert_app_registration(
        session,
        base_url=web,
        app_id=app_id,
        slug=slug,
        client_id=data.get("client_id"),
        private_key_ciphertext=encrypt(data["pem"]),
        webhook_secret_ciphertext=(
            encrypt(data["webhook_secret"]) if data.get("webhook_secret") else None
        ),
        client_secret_ciphertext=(
            encrypt(data["client_secret"]) if data.get("client_secret") else None
        ),
    )

    # Rotate the state across the second leg (single-use per hop).
    new_state = secrets.token_urlsafe(32)
    request.session[_SESSION_KEY] = {
        "state": new_state,
        "base_url": web,
        "writable": bool(saved.get("writable", True)),
    }
    return RedirectResponse(_install_url(web, slug, new_state), status_code=303)


async def _resolve_installation(
    app_id: str, pem: str, installation_id: int, api_base: str
) -> tuple[str, list[str] | None]:
    """Resolve the installation's owner + repo selection from the real install (honest-state).

    Owner comes from the installation's account; the allowlist is the actual selected-repos
    set (``None`` when the install grants all repos). Never guessed.
    """
    from githubkit import AppAuthStrategy, AppInstallationAuthStrategy, GitHub

    app_gh = GitHub(AppAuthStrategy(app_id, pem), base_url=api_base)
    inst = (await app_gh.arequest("GET", f"/app/installations/{installation_id}")).json()
    owner = (inst.get("account") or {}).get("login")
    if not owner:
        raise RuntimeError(f"installation {installation_id} has no resolvable account owner")

    allowlist: list[str] | None = None
    if inst.get("repository_selection") == "selected":
        inst_gh = GitHub(
            AppInstallationAuthStrategy(app_id, pem, int(installation_id)), base_url=api_base
        )
        repos = (
            await inst_gh.arequest(
                "GET", "/installation/repositories", params={"per_page": 100}
            )
        ).json()
        allowlist = [r["name"] for r in (repos.get("repositories") or [])]
    return owner, allowlist


@router.get("/installed", include_in_schema=False)
async def app_installed(
    request: Request,
    installation_id: int = Query(...),
    setup_action: str | None = Query(None),
    state: str | None = Query(None),
    session: AsyncSession = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> Response:
    """App ``setup_url``: create the connection from the real installation, then return to SPA."""
    saved = request.session.get(_SESSION_KEY) or {}
    if not saved.get("state") or not state or not secrets.compare_digest(str(saved["state"]), state):
        return _reject("state mismatch")
    web = str(saved["base_url"])

    reg = await get_app_registration(session, web)
    if reg is None:
        log.warning("github_app.no_registration", base_url=web)
        return _spa_error("no_registration")

    pem = decrypt(reg.private_key_ciphertext)
    try:
        owner, allowlist = await _resolve_installation(
            reg.app_id, pem, int(installation_id), github_api_base(web)
        )
    except Exception as exc:  # noqa: BLE001 — log cause server-side, generic message to UI
        log.warning("github_app.install_lookup_failed", base_url=web, error=str(exc))
        return _spa_error("installation_lookup_failed")

    conn = await add_connection(
        session,
        provider_type="github",
        label=f"gh:{owner}",
        scope=f"org · {owner}",
        auth_mode="GitHub App",
        credential=pem,
        writable=bool(saved.get("writable", True)),
        app_id=reg.app_id,
        installation_id=int(installation_id),
        owner=owner,
        repo_allowlist=allowlist,
        base_url=web,
    )
    request.session.pop(_SESSION_KEY, None)

    # The scheduled poller picks the new connection up on its next cycle (same as a manual
    # add); no synchronous/eager provider call on this redirect.
    log.info("github_app.connected", connection=conn.id, base_url=web, owner=owner)
    return RedirectResponse(f"/providers?connected={conn.id}", status_code=303)


async def _uninstall_one_installation(
    app_id: str, pem: str, installation_id: int, api_base: str
) -> tuple[bool, str | None]:
    """Uninstall one org's installation via the App JWT. Best-effort and idempotent.

    Returns ``(uninstalled, deep_link)``: ``(True, None)`` when the installation is gone (a
    404 counts — already uninstalled); ``(False, <installation settings URL>)`` when it could
    not be removed, so the operator can finish it by hand.
    """
    from githubkit import AppAuthStrategy, GitHub

    app_gh = GitHub(AppAuthStrategy(app_id, pem), base_url=api_base)
    html_url: str | None = None
    try:  # the lookup only feeds the fallback deep link — never fatal
        inst = (await app_gh.arequest("GET", f"/app/installations/{installation_id}")).json()
        html_url = inst.get("html_url") or None
    except Exception:  # noqa: BLE001
        pass
    try:
        await app_gh.arequest("DELETE", f"/app/installations/{installation_id}")
        return True, None
    except Exception as exc:  # noqa: BLE001 — a failure yields a manual-uninstall link, not an abort
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 404:  # already uninstalled — idempotent success
            return True, None
        log.warning(
            "github_app.uninstall_one_failed", installation=installation_id, error=str(exc)
        )
        return False, html_url


class RemoveConnectionResult(BaseModel):
    """Outcome of removing one connection (= one org). For a GitHub-App connection this also
    reflects the GitHub-side cleanup; for other providers only ``org``/``removed`` are set."""

    org: str | None = None  # the org/owner login, when known
    removed: bool = True  # the Hangar connection was dropped
    uninstalled: bool = False  # the org's App installation was removed on GitHub
    uninstall_url: str | None = None  # per-org deep link to finish uninstalling (auto failed)
    app_forgotten: bool = False  # this was the App's last connection → registration discarded
    delete_app_url: str | None = None  # deep link to finish deleting the App itself on GitHub


async def remove_github_app_connection(
    session: AsyncSession, row: ConnectionRow, actor: str
) -> RemoveConnectionResult:
    """Remove one GitHub-App-backed connection — i.e. drop one org from the App.

    Uninstalls that org's installation on GitHub (best-effort, using the App key while it is
    still held), drops the Hangar connection, and — when this was the App's **last** remaining
    connection — forgets the stored App registration and returns the deep link to finish
    deleting the App itself (GitHub has no delete-App API). Ordering follows Constitution III:
    act on GitHub while the credential exists, *then* discard it. Audited as one entry.
    """
    web = github_web_base(row.base_url or "https://github.com")
    reg = await get_app_registration(session, web)

    uninstalled, uninstall_url = False, None
    if reg is not None and row.installation_id is not None:
        pem = decrypt(reg.private_key_ciphertext)
        uninstalled, uninstall_url = await _uninstall_one_installation(
            reg.app_id, pem, int(row.installation_id), github_api_base(web)
        )

    # Other connections still backed by this App (same host + app_id) — the ones keeping it alive.
    siblings = [
        r
        for r in await repo_store.list_connection_rows_for_base_url(session, web)
        if r.app_id == row.app_id and r.id != row.id
    ]
    await remove_connection(session, row.id)

    delete_app_url: str | None = None
    app_forgotten = False
    if reg is not None and not siblings:  # last one out → retire the App
        await repo_store.delete_app_registration(session, web)
        delete_app_url = github_app_delete_url(web, reg.slug)
        app_forgotten = True

    await record_correction(
        session,
        actor=actor,
        connection_label=row.label or f"gh:{row.owner}",
        repo_id="-",
        check_label="Connection removed",
        result=(
            f"removed {row.owner or row.id}"
            + (" · uninstalled on GitHub" if uninstalled else "")
            + (f" · forgot App {reg.slug}" if app_forgotten and reg else "")
        ),
        pr_url=delete_app_url or "",
    )
    log.info(
        "github_app.connection_removed",
        connection=row.id,
        owner=row.owner,
        uninstalled=uninstalled,
        app_forgotten=app_forgotten,
    )
    return RemoveConnectionResult(
        org=row.owner,
        removed=True,
        uninstalled=uninstalled,
        uninstall_url=uninstall_url,
        app_forgotten=app_forgotten,
        delete_app_url=delete_app_url,
    )
