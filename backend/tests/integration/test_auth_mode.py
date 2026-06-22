"""T067 — fail-closed startup gate (FR-029/FR-030)."""

from __future__ import annotations

import pytest

from hangar.config import AccessMode, Settings, StartupError, validate_startup


def test_unset_forward_auth_raises() -> None:
    settings = Settings(forward_auth=None, host="127.0.0.1")
    assert settings.access_mode is None
    with pytest.raises(StartupError):
        validate_startup(settings)


def test_disabled_mode_returns_warning() -> None:
    settings = Settings(forward_auth="disabled", host="127.0.0.1")
    assert settings.access_mode is AccessMode.disabled
    warnings = validate_startup(settings)
    assert any("disabled" in w.lower() for w in warnings)


def test_public_bind_without_allow_raises() -> None:
    # A genuinely public address must trip the bind gate.
    settings = Settings(forward_auth="disabled", host="8.8.8.8", allow_public_bind=False)
    assert settings.binds_public is True
    with pytest.raises(StartupError):
        validate_startup(settings)


def test_public_bind_with_allow_does_not_raise() -> None:
    settings = Settings(forward_auth="disabled", host="8.8.8.8", allow_public_bind=True)
    # should not raise; returns warnings list
    warnings = validate_startup(settings)
    assert isinstance(warnings, list)


def test_unspecified_host_is_public_and_trips_gate() -> None:
    """0.0.0.0 / :: bind to every interface and MUST trip the public-bind gate (FR-030),
    regardless of how ``ipaddress`` classifies the unspecified address on a given Python
    (on 3.14 ``is_private`` is True for 0.0.0.0, so ``binds_public`` checks ``is_unspecified``).
    """
    for host in ("0.0.0.0", "::"):
        settings = Settings(forward_auth="disabled", host=host, allow_public_bind=False)
        assert settings.binds_public is True, host
        with pytest.raises(StartupError):
            validate_startup(settings)
    # ...and is allowed once the operator explicitly opts in.
    ok = Settings(forward_auth="disabled", host="0.0.0.0", allow_public_bind=True)
    assert isinstance(validate_startup(ok), list)


def test_forward_auth_without_trust_warns_not_raises() -> None:
    settings = Settings(forward_auth="enabled", host="127.0.0.1")
    warnings = validate_startup(settings)
    assert any("trusted" in w.lower() or "rejected" in w.lower() for w in warnings)
