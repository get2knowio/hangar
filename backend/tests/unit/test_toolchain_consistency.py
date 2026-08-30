"""The toolchain declarations must agree with each other.

A principle that isn't a test is a suggestion. Four files independently name a
Python version, and nothing but habit kept them equal:

* ``backend/pyproject.toml`` — ``project.requires-python``, ``tool.ruff.target-version``,
  and ``tool.mypy.python_version``
* ``mise.toml`` — the ``[tools].python`` pin every task and CI leg resolves through
* ``.github/workflows/ci.yml`` — the matrix that decides which interpreters are
  actually exercised

The failure this guards against is quiet: lint and type configuration targeting an
interpreter the package refuses to install on, or a ``requires-python`` range whose
floor no CI job ever runs. Both look green.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

_BACKEND = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND.parent


def _pyproject() -> dict:
    with (_BACKEND / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def _mise() -> dict:
    with (_REPO_ROOT / "mise.toml").open("rb") as fh:
        return tomllib.load(fh)


def _ci() -> dict:
    with (_REPO_ROOT / ".github" / "workflows" / "ci.yml").open() as fh:
        return yaml.safe_load(fh)


def _requires_python_bounds() -> tuple[str, str]:
    """(floor, exclusive-ceiling) parsed from ``requires-python``."""
    spec = _pyproject()["project"]["requires-python"]
    floor = re.search(r">=\s*(\d+\.\d+)", spec)
    ceiling = re.search(r"<\s*(\d+\.\d+)", spec)
    assert floor, f"requires-python must declare a floor with >=: {spec!r}"
    assert ceiling, (
        f"requires-python must declare an upper bound: {spec!r}. An open-ended range "
        "claims interpreters no CI job exercises."
    )
    return floor.group(1), ceiling.group(1)


def test_lint_and_type_config_target_the_declared_floor() -> None:
    """ruff and mypy must target the interpreter the package actually installs on."""
    floor, _ = _requires_python_bounds()
    cfg = _pyproject()["tool"]

    ruff_target = cfg["ruff"]["target-version"]
    assert ruff_target == "py" + floor.replace(".", ""), (
        f"ruff target-version is {ruff_target!r} but requires-python's floor is {floor}"
    )

    mypy_version = cfg["mypy"]["python_version"]
    assert mypy_version == floor, (
        f"mypy python_version is {mypy_version!r} but requires-python's floor is {floor}"
    )


def test_mise_pins_the_declared_floor() -> None:
    """The toolchain mise installs is the floor, so local runs exercise it by default."""
    floor, _ = _requires_python_bounds()
    pinned = str(_mise()["tools"]["python"])
    assert pinned == floor, (
        f"mise.toml pins python {pinned!r} but requires-python's floor is {floor}"
    )


def test_ci_matrix_exercises_both_ends_of_the_declared_range() -> None:
    """Neither the floor nor the top supported interpreter may go untested."""
    floor, ceiling = _requires_python_bounds()
    matrix = _ci()["jobs"]["backend-matrix"]["strategy"]["matrix"]["python-version"]
    tested = {str(v) for v in matrix}

    assert floor in tested, (
        f"requires-python declares floor {floor} but the CI matrix tests {sorted(tested)}. "
        "An unexercised floor is a claim nobody is keeping."
    )

    # The highest interpreter the range admits: `<3.15` means 3.14 is the ceiling.
    major, minor = (int(p) for p in ceiling.split("."))
    top = f"{major}.{minor - 1}"
    assert top in tested, (
        f"requires-python admits up to {top} but the CI matrix tests {sorted(tested)}. "
        "Either test it or lower the upper bound."
    )


def test_required_status_check_job_names_carry_no_version() -> None:
    """Required checks must stay version-free or a runtime bump blocks every open PR.

    ``Backend`` and ``Frontend`` are the protected names; the matrix job deliberately
    carries a version and is deliberately not the required check.
    """
    jobs = _ci()["jobs"]
    for job_id in ("backend", "frontend"):
        name = jobs[job_id].get("name", job_id)
        assert not re.search(r"\d+\.\d+|\$\{\{", name), (
            f"CI job {job_id!r} is named {name!r}. Required-check names must not embed a "
            "version or a matrix expression."
        )

    # The gate must actually depend on the matrix, or it would pass while a leg failed.
    assert "backend-matrix" in jobs["backend"]["needs"]


@pytest.mark.parametrize("group", ["test", "lint", "dev"])
def test_dev_tooling_lives_in_dependency_groups(group: str) -> None:
    """Extras are what a consumer installs; dev tooling belongs in PEP 735 groups."""
    pyproject = _pyproject()
    assert group in pyproject["dependency-groups"]
    # `dev` is the only extra a consumer should never see offered.
    assert "dev" not in pyproject["project"].get("optional-dependencies", {})
