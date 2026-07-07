"""Per-rule reference links (``Check.doc_url``) surfaced on the catalog & policy page.

Each catalog check may carry a ``doc_url`` pointing at the canonical explanation of the rule
(the tool/spec/docs it validates). The catalog is the **single source of truth**; the README's
check catalog mirrors those links, and the drift test below fails if the two diverge — so a
URL can't be changed in one place and go stale in the other (Constitution: typed contracts,
single-sourced shared values).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from hangar.domain.checks import CATALOG, all_checks

_README = Path(__file__).parents[3] / "README.md"


def _checks_with_doc_url() -> list:
    return [c for c in all_checks() if c.doc_url]


def test_some_rules_carry_a_reference_link() -> None:
    # A representative spread across groups — guards against the field silently regressing.
    assert CATALOG["release_please"].doc_url == "https://github.com/googleapis/release-please"
    assert CATALOG["code_scanning"].doc_url == "https://codeql.github.com/"
    assert CATALOG["dependabot_alerts"].doc_url is not None
    # ...and the coverage is broad, not a token one-off.
    assert len(_checks_with_doc_url()) >= 12


def test_doc_urls_are_well_formed_https() -> None:
    for c in _checks_with_doc_url():
        assert c.doc_url and c.doc_url.startswith("https://"), c.id


def test_hangar_specific_rules_have_no_reference_link() -> None:
    # These are Hangar concepts with no external canonical page — they must stay None rather
    # than point somewhere misleading (honest state).
    for cid in ("release_health", "description", "default_branch"):
        assert CATALOG[cid].doc_url is None, cid


def test_readme_mirrors_every_catalog_doc_url() -> None:
    """Drift guard: every rule reference in the catalog must appear in the README.

    The catalog is canonical; the README is a mirror. If someone adds or changes a ``doc_url``
    without updating the README (or vice-versa), this fails and names the offenders.
    """
    readme = _README.read_text(encoding="utf-8")
    missing = [(c.id, c.doc_url) for c in _checks_with_doc_url() if c.doc_url not in readme]
    assert not missing, f"doc_url(s) not linked in README.md: {missing}"


def test_catalog_endpoint_exposes_doc_url(client: TestClient) -> None:
    """The /catalog payload carries doc_url per check (null where the rule has no reference)."""
    body = client.get("/api/v1/catalog").json()
    by_id = {c["id"]: c for grp in body["groups"] for c in grp["checks"]}
    assert "doc_url" in by_id["release_please"]
    assert by_id["release_please"]["doc_url"] == "https://github.com/googleapis/release-please"
    assert by_id["release_health"]["doc_url"] is None
