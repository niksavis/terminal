from __future__ import annotations

import sys
from pathlib import Path

import pytest

from terminal_setup import platform
from terminal_setup.platform import SETUP_SOURCE, rerun_command, setup_command

ROOT = Path(__file__).resolve().parents[2]


def test_a_clone_run_names_the_clone_command() -> None:
    assert setup_command("--only report", argv0="/repo/setup-terminal.py") == (
        "uv run python setup-terminal.py --only report"
    )


@pytest.mark.parametrize(
    "argv0",
    [
        "/home/dev/.cache/uv/archive-v0/x/bin/terminal-setup",
        "C:\\Users\\dev\\AppData\\Local\\uv\\cache\\archive-v0\\x\\Scripts\\terminal-setup",
    ],
)
def test_a_uvx_run_names_the_uvx_command(argv0: str) -> None:
    assert setup_command("--only report", argv0=argv0) == (
        f"uvx --from {SETUP_SOURCE} terminal-setup --only report"
    )


def test_rerun_command_repeats_the_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["terminal-setup", "--unattended", "--agents", "all"])

    assert rerun_command() == f"uvx --from {SETUP_SOURCE} terminal-setup --unattended --agents all"


@pytest.mark.parametrize("module", ["cli", "prerequisites", "configs", "agents", "release_install"])
def test_no_hint_names_a_command_that_is_not_on_path(module: str) -> None:
    source = (ROOT / "terminal_setup" / f"{module}.py").read_text(encoding="utf-8").lower()

    for stale in (
        "re-run this setup",
        "re-run terminal-setup",
        "rerun with --",
        "with: terminal-setup",
    ):
        assert stale not in source


def test_setup_source_is_the_one_the_readme_names() -> None:
    assert platform.SETUP_SOURCE in (ROOT / "README.md").read_text(encoding="utf-8")
