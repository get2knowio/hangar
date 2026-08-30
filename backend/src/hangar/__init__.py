"""Hangar — provider-agnostic fleet control plane."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hangar")
except PackageNotFoundError:  # pragma: no cover - source tree without an install
    __version__ = "0.0.0.dev0+unknown"

__all__ = ["__version__"]
