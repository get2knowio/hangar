"""Gitea HTTP client + host derivation — the only place Gitea URLs are built (Constitution I).

Gitea is always self-hosted, so the connection's opaque ``base_url`` *is* the instance's
browser host; the REST API hangs off ``{base_url}/api/v1`` and authenticates with a scoped
personal access token sent as ``Authorization: token <pat>``. Reads follow the same
404→absent / 403→unreadable convention the GitHub adapter uses, surfaced as sentinels so a
missing resource degrades a single check to ``fail``/``unknown`` rather than aborting the
snapshot (Constitution VI/VIII).
"""

from __future__ import annotations

from types import TracebackType

import httpx

from hangar.domain.models import ProviderConnection


class _Sentinel:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{self.name}>"


# A read outcome that isn't a JSON body: absent (404), unreadable (401/403), or empty (204).
_NOT_FOUND = _Sentinel("NOT_FOUND")
_FORBIDDEN = _Sentinel("FORBIDDEN")
_NO_CONTENT = _Sentinel("NO_CONTENT")


def gitea_web_base(base_url: str | None) -> str:
    """The Gitea instance's browser host with no trailing slash."""
    return (base_url or "").rstrip("/")


def gitea_api_base(base_url: str | None) -> str:
    """The REST API base for a Gitea instance: ``{base_url}/api/v1``."""
    return f"{gitea_web_base(base_url)}/api/v1"


class GiteaClient:
    """A thin async wrapper over ``httpx.AsyncClient`` scoped to one connection.

    ``get`` returns the decoded JSON body or a sentinel (``_NOT_FOUND``/``_FORBIDDEN``/
    ``_NO_CONTENT``); a 5xx (or transport error) propagates so the caller can degrade that
    repo to its last good snapshot rather than caching a half-built one.
    """

    def __init__(self, connection: ProviderConnection, *, timeout: float) -> None:
        if not connection.token:
            raise RuntimeError(
                f"Gitea connection '{connection.id}' has no decrypted credential attached; "
                "cannot authenticate (call attach_credential before using the adapter)."
            )
        self._base = gitea_api_base(connection.base_url)
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"token {connection.token}",
                "Accept": "application/json",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    async def __aenter__(self) -> GiteaClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict | None = None) -> object:
        """GET ``{api_base}{path}``; return the JSON body or a status sentinel."""
        resp = await self._client.get(f"{self._base}{path}", params=params)
        if resp.status_code == 404:
            return _NOT_FOUND
        if resp.status_code in (401, 403):
            return _FORBIDDEN
        if resp.status_code == 204:
            return _NO_CONTENT
        resp.raise_for_status()
        return resp.json()

    async def post(self, path: str, json: dict) -> dict:
        """POST ``{api_base}{path}``; return the created resource. Raises on any non-2xx so a
        failed write never looks like a success (no silent no-op, Constitution VIII)."""
        resp = await self._client.post(f"{self._base}{path}", json=json)
        resp.raise_for_status()
        return resp.json()
