"""Security hygiene: a provider failure must not echo its raw exception (credential
fragments / internal URLs) to the client, and CORS is scoped to the verbs/headers the SPA
uses rather than a wildcard."""

from __future__ import annotations


def test_list_repos_502_hides_raw_provider_error(client, monkeypatch) -> None:
    import hangar.api.providers as providers_api

    class _Boom:
        async def list_repo_listings(self, _conn):
            raise RuntimeError("token ghp_SECRET and https://internal.host leaked here")

    monkeypatch.setattr(providers_api, "provider_for", lambda _conn: _Boom())

    r = client.get("/api/v1/providers/gh-main/repos")
    assert r.status_code == 502
    detail = r.json()["detail"]
    # The raw exception text (and anything sensitive it carried) must not reach the client.
    assert "ghp_SECRET" not in detail
    assert "internal.host" not in detail
    assert "Couldn't list repositories" in detail


def test_cors_is_scoped_not_wildcard(client) -> None:
    r = client.options(
        "/api/v1/providers",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    # Starlette merges the CORS-safelisted headers in, but the configured surface is an
    # explicit list — never a wildcard — for both headers and methods.
    allow_headers = r.headers.get("access-control-allow-headers") or ""
    assert "*" not in allow_headers and "Content-Type" in allow_headers
    methods = r.headers.get("access-control-allow-methods") or ""
    assert "*" not in methods and "GET" in methods
