from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import real_tools_env

MIN_PYTHON_VERSION = (3, 14)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _has_version_line(output: str, expected_prefix: str) -> bool:
    return any(line.startswith(expected_prefix) for line in output.splitlines())


def test_python_version() -> None:
    assert sys.version_info >= MIN_PYTHON_VERSION, (
        f"Expected Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+, got {sys.version}"
    )


def test_pyproject_exists() -> None:
    pyproject = PROJECT_ROOT / "pyproject.toml"
    assert pyproject.is_file(), "pyproject.toml should exist"


def test_uv_available() -> None:
    result = subprocess.run(
        ["uv", "--version"],
        capture_output=True,
        text=True,
        check=False,
        env=real_tools_env(),
    )
    assert result.returncode == 0, f"uv --version failed: {result.stderr}"
    assert result.stdout.startswith("uv "), f"Unexpected uv version output: {result.stdout}"


@pytest.mark.parametrize(
    ("tool", "expected_prefix"),
    [
        ("ruff", "ruff "),
        ("pytest", "pytest "),
        ("pyright", "pyright "),
    ],
)
def test_dev_tool_available(tool: str, expected_prefix: str) -> None:
    result = subprocess.run(
        ["uv", "run", tool, "--version"],
        capture_output=True,
        text=True,
        check=False,
        cwd=PROJECT_ROOT,
        env=real_tools_env(),
    )
    assert result.returncode == 0, f"{tool} --version failed: {result.stderr}"
    assert _has_version_line(result.stdout, expected_prefix), (
        f"Unexpected {tool} version output: {result.stdout}"
    )
