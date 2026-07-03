"""Parsing + validation of the in-repo ``.hangar.json`` config (defensive boundary)."""

from __future__ import annotations

from hangar.domain.repo_config import HangarRepoConfig


def test_parses_object_entries_with_reason() -> None:
    raw = """
    {
      "version": 1,
      "ignore": [
        {"check": "dependabot_alerts", "reason": "Internal tool, no external deps"},
        {"check": "code_scanning"}
      ]
    }
    """
    config = HangarRepoConfig.parse(raw)
    assert config is not None
    assert config.suppressions() == {
        "dependabot_alerts": "Internal tool, no external deps",
        "code_scanning": "",
    }


def test_accepts_bare_string_shorthand() -> None:
    config = HangarRepoConfig.parse('{"ignore": ["readme", "license"]}')
    assert config is not None
    assert config.suppressions() == {"readme": "", "license": ""}


def test_drops_unknown_check_ids() -> None:
    raw = '{"ignore": ["license", {"check": "not_a_real_check"}, "no_such_thing"]}'
    config = HangarRepoConfig.parse(raw)
    assert config is not None
    # Only the known catalog id survives — unknowns are dropped, not fatal.
    assert config.suppressions() == {"license": ""}


def test_malformed_json_returns_none() -> None:
    assert HangarRepoConfig.parse("{not json") is None
    assert HangarRepoConfig.parse("") is None


def test_non_object_top_level_returns_none() -> None:
    assert HangarRepoConfig.parse('["license"]') is None
    assert HangarRepoConfig.parse('"license"') is None


def test_missing_ignore_key_is_empty_not_error() -> None:
    config = HangarRepoConfig.parse('{"version": 1}')
    assert config is not None
    assert config.suppressions() == {}


def test_ignores_malformed_entries_but_keeps_valid_ones() -> None:
    # A number, a null, and an object without a string `check` are all skipped.
    raw = '{"ignore": [123, null, {"reason": "x"}, {"check": 5}, "readme"]}'
    config = HangarRepoConfig.parse(raw)
    assert config is not None
    assert config.suppressions() == {"readme": ""}


def test_non_string_reason_falls_back_to_empty() -> None:
    config = HangarRepoConfig.parse('{"ignore": [{"check": "readme", "reason": 42}]}')
    assert config is not None
    assert config.suppressions() == {"readme": ""}


def test_non_int_version_tolerated() -> None:
    config = HangarRepoConfig.parse('{"version": "1", "ignore": ["readme"]}')
    assert config is not None
    assert config.version == 1
    assert config.suppressions() == {"readme": ""}
