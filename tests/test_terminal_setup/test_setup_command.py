from __future__ import annotations

import sys
from pathlib import Path

import pytest

from terminal_setup import platform
from terminal_setup.platform import (
    SETUP_ARCHIVES,
    SETUP_SOURCE,
    installed_source,
    rerun_command,
    setup_command,
)

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
        f"uvx --refresh-package terminal --from {SETUP_SOURCE} terminal-setup --only report"
    )


def test_a_release_run_names_the_release_it_ran_from() -> None:
    release = f"{SETUP_ARCHIVES}v0.12.3.zip"

    assert setup_command("--only report", argv0="terminal-setup", source=release) == (
        f"uvx --from {release} terminal-setup --only report"
    )


def test_a_branch_run_refreshes_the_branch_it_ran_from() -> None:
    branch = f"{SETUP_ARCHIVES}feature.zip"

    assert setup_command("--only report", argv0="terminal-setup", source=branch) == (
        f"uvx --refresh-package terminal --from {branch} terminal-setup --only report"
    )


def test_installed_source_reads_the_archive_that_uv_installed() -> None:
    release = f"{SETUP_ARCHIVES}v0.12.3.zip"
    record = f'{{"url":"{release}","archive_info":{{}}}}'

    assert installed_source(record) == release


@pytest.mark.parametrize(
    "record",
    [
        "",
        "not json",
        "[]",
        '{"url":"file:///repo","dir_info":{"editable":true}}',
        '{"url":"https://example.com/archive/v1.0.0.zip","archive_info":{}}',
        '{"url":"https://github.com/niksavis/terminal","vcs_info":{"vcs":"git"}}',
    ],
)
def test_installed_source_falls_back_to_main_for_any_other_install(record: str) -> None:
    assert installed_source(record) == SETUP_SOURCE


def test_rerun_command_repeats_the_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["terminal-setup", "--unattended", "--agents", "all"])

    base = f"uvx --refresh-package terminal --from {SETUP_SOURCE} terminal-setup"
    assert rerun_command() == f"{base} --unattended --agents all"


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


@pytest.mark.parametrize(
    "document",
    [
        "README.md",
        "terminal-cheat-sheet.md",
        "terminal_setup/templates/img-zoom-skill.md",
    ],
)
def test_user_documents_need_no_git_to_run_setup(document: str) -> None:
    text = (ROOT / document).read_text(encoding="utf-8")

    assert "--from git+" not in text


def test_documented_setup_commands_use_the_one_source() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cheat_sheet = (ROOT / "terminal-cheat-sheet.md").read_text(encoding="utf-8")

    assert setup_command("--update", argv0="terminal-setup") in readme + cheat_sheet
    assert setup_command("--only report", argv0="terminal-setup") in readme + cheat_sheet
