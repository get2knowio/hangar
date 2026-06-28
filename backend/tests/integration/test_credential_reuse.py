"""Reusing one stored credential across connections to the same provider (FR-022/FR-032).

A single PAT often spans several orgs; the add-connection flow can point at an existing
same-provider connection instead of re-pasting the secret. Fail-closed: the source must
exist, match the provider, and actually hold a credential.
"""

from __future__ import annotations


def test_reuse_credential_from_existing_connection(client) -> None:
    r1 = client.post("/api/v1/providers", json={
        "provider_type": "github", "label": "gh:org-a", "scope": "org · org-a",
        "credential": "ghp_shared_token", "owner": "org-a",
    })
    assert r1.status_code == 201
    assert r1.json()["has_credential"] is True

    # Second connection reuses the first's credential — none pasted — and is writable,
    # which is only allowed because a credential is present (least-privilege gate).
    r2 = client.post("/api/v1/providers", json={
        "provider_type": "github", "label": "gh:org-b", "scope": "org · org-b",
        "owner": "org-b", "copy_credential_from": "gh-org-a", "writable": True,
    })
    assert r2.status_code == 201
    card = r2.json()
    assert card["has_credential"] is True
    assert card["writes"] is True


def test_reuse_from_unknown_connection_is_400(client) -> None:
    r = client.post("/api/v1/providers", json={
        "provider_type": "github", "label": "gh:x", "scope": "x", "copy_credential_from": "nope",
    })
    assert r.status_code == 400


def test_reuse_across_providers_is_400(client) -> None:
    client.post("/api/v1/providers", json={
        "provider_type": "github", "label": "gh:a", "scope": "a",
        "credential": "ghp_t", "owner": "a",
    })
    r = client.post("/api/v1/providers", json={
        "provider_type": "gitea", "label": "gitea:b", "scope": "b", "copy_credential_from": "gh-a",
    })
    assert r.status_code == 400


def test_reuse_from_credentialless_connection_is_400(client) -> None:
    # Seeded demo connections hold no credential, so there is nothing to reuse.
    r = client.post("/api/v1/providers", json={
        "provider_type": "github", "label": "gh:new", "scope": "new",
        "copy_credential_from": "gh-main",
    })
    assert r.status_code == 400
