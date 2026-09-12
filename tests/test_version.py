"""The package version is declared twice; this is what keeps the two in step."""

from __future__ import annotations

import tomllib
from pathlib import Path

import terminal_setup

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def declared_version() -> str:
    """Return the version in pyproject.toml, which the release process bumps."""
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def test_package_version_matches_pyproject() -> None:
    """A second copy of the version drifts unless something fails when it does.

    `__version__` sat at 0.1.0 through every release up to 0.5.0 because the
    release process bumps pyproject alone and nothing compared the two.
    """
    assert terminal_setup.__version__ == declared_version()
