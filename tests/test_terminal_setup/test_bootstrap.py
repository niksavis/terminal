from __future__ import annotations

from pathlib import Path

import pytest

from terminal_setup.prerequisites import TARGET_PYTHON_MINOR

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("script", ["install.sh", "install.ps1"])
def test_bootstrap_runs_setup_on_the_target_python(script: str) -> None:
    text = (ROOT / script).read_text(encoding="utf-8")

    assert f"uvx --python {TARGET_PYTHON_MINOR} --refresh-package terminal" in text


@pytest.mark.parametrize("script", ["install.sh", "install.ps1"])
def test_bootstrap_builds_from_an_archive_so_git_is_not_needed(script: str) -> None:
    text = (ROOT / script).read_text(encoding="utf-8")

    assert "https://github.com/niksavis/terminal/archive/" in text
    assert "git+" not in text


def test_readme_names_both_bootstrap_scripts() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for script in ("install.sh", "install.ps1"):
        assert f"https://raw.githubusercontent.com/niksavis/terminal/main/{script}" in readme
