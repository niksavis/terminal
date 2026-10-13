from __future__ import annotations

from pathlib import Path

import pytest

from terminal_setup.prerequisites import BOOTSTRAP_MARKER, TARGET_PYTHON_MINOR

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


def test_readme_names_both_bootstrap_scripts_of_the_latest_release() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for script in ("install.sh", "install.ps1"):
        assert f"https://github.com/niksavis/terminal/releases/latest/download/{script}" in readme


USER_DOCS = (
    "README.md",
    "terminal-cheat-sheet.md",
    "docs/user-guide.md",
    "docs/contributing.md",
    "docs/what-gets-installed.md",
    "docs/windows-wsl-setup.md",
)


@pytest.mark.parametrize("doc", USER_DOCS)
def test_a_user_doc_never_tells_a_user_to_install_from_main(doc: str) -> None:
    lines = (ROOT / doc).read_text(encoding="utf-8").splitlines()

    commands = [
        line
        for line in lines
        if ("raw.githubusercontent.com/niksavis/terminal/main/install" in line)
        or ("archive/main.zip" in line and not line.startswith("→ "))
    ]
    assert commands == []


def test_powershell_bootstrap_updates_uv_before_uvx_runs() -> None:
    text = (ROOT / "install.ps1").read_text(encoding="utf-8")

    assert text.index("uv self update") < text.index("uvx --python")
    assert "$setupArgs -contains '--update'" in text


def test_powershell_bootstrap_clears_its_arguments_variable() -> None:
    text = (ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "Remove-Item Env:TERMINAL_SETUP_ARGS" in text


def test_powershell_bootstrap_marks_and_unmarks_its_run() -> None:
    text = (ROOT / "install.ps1").read_text(encoding="utf-8")

    assert f"$env:{BOOTSTRAP_MARKER} = '1'" in text
    assert f"Remove-Item Env:{BOOTSTRAP_MARKER}" in text
