from __future__ import annotations

import shlex
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

from terminal_setup import prerequisites
from terminal_setup.platform import OperatingSystem, PackageManager, wsl_exec_command
from terminal_setup.prerequisites import (
    PYTHON_INSTALLED_QUERY,
    UV_PYTHON_INSTALL_ARGS,
    UV_PYTHON_MANAGED_ARGS,
    UV_PYTHON_UPGRADE_ARGS,
    ensure_python,
    python_meets_target,
)

from .test_runner import CapturingReporter
from .test_unattended import RecordingRunner, _windows_platform

UV = 'PATH="$HOME/.local/bin:$PATH"; uv '
WSL_QUERY = tuple(wsl_exec_command("Ubuntu", ["sh", "-c", PYTHON_INSTALLED_QUERY]))
WSL_MANAGED = tuple(
    wsl_exec_command("Ubuntu", ["sh", "-c", UV + shlex.join(UV_PYTHON_MANAGED_ARGS)])
)
WSL_INSTALL = wsl_exec_command("Ubuntu", ["sh", "-c", UV + shlex.join(UV_PYTHON_INSTALL_ARGS)])
WSL_UPGRADE = wsl_exec_command("Ubuntu", ["sh", "-c", UV + shlex.join(UV_PYTHON_UPGRADE_ARGS)])
WINDOWS_UV = "C:/uv/uv.exe"


@pytest.mark.parametrize(
    ("version", "expected"),
    [(None, False), ("3.12.3", False), ("3.13.9", False), ("3.14.0", True), ("3.15.1", True)],
)
def test_python_meets_target(version: str | None, *, expected: bool) -> None:
    assert python_meets_target(version) is expected


class WindowsRunner(RecordingRunner):
    def which(self, command: str) -> str | None:
        return {"uv": WINDOWS_UV, "python": "C:/py/python.exe"}.get(command)


def _run(runner: RecordingRunner, *, update: bool = False, tmp_home: Path | None = None) -> None:
    platform = _windows_platform()
    if tmp_home is not None:
        platform = replace(platform, home=tmp_home)
    with mock.patch.object(prerequisites, "is_running_in_wsl", return_value=False):
        ensure_python(runner, platform, update=update)


@pytest.mark.parametrize("installed", ["", "3.12.3\n"])
def test_wsl_installs_python_when_missing_or_older(installed: str) -> None:
    runner = RecordingRunner(reporter=CapturingReporter(), outputs={WSL_QUERY: (0, installed)})

    _run(runner)

    assert WSL_INSTALL in runner.commands


def test_wsl_skips_a_present_python_without_update() -> None:
    runner = RecordingRunner(reporter=CapturingReporter(), outputs={WSL_QUERY: (0, "3.14.6\n")})

    _run(runner)

    assert WSL_INSTALL not in runner.commands
    assert WSL_UPGRADE not in runner.commands
    assert ("success", "Python 3.14.6 is present") in runner.reporter.messages  # type: ignore[attr-defined]


@pytest.mark.parametrize(("managed", "upgraded"), [(0, True), (2, False)])
def test_wsl_update_upgrades_only_a_uv_managed_python(*, managed: int, upgraded: bool) -> None:
    runner = RecordingRunner(
        reporter=CapturingReporter(),
        outputs={WSL_QUERY: (0, "3.14.6\n"), WSL_MANAGED: (managed, "")},
    )

    _run(runner, update=True)

    assert (WSL_UPGRADE in runner.commands) is upgraded
    assert WSL_INSTALL not in runner.commands


def test_windows_without_uv_records_a_failed_step() -> None:
    runner = RecordingRunner(reporter=CapturingReporter(), outputs={WSL_QUERY: (0, "3.14.6\n")})

    _run(runner)

    assert runner.failures == ["install Python on Windows"]


def test_windows_skips_a_present_python() -> None:
    runner = WindowsRunner(
        reporter=CapturingReporter(),
        outputs={
            WSL_QUERY: (0, "3.14.6\n"),
            ("python", "-c", prerequisites.PYTHON_VERSION_CODE): (0, "3.14.7\n"),
        },
    )

    _run(runner)

    assert [WINDOWS_UV, *UV_PYTHON_INSTALL_ARGS] not in runner.commands
    assert runner.failures == []


def test_windows_installs_python_and_adds_the_bin_dir(tmp_path: Path) -> None:
    runner = WindowsRunner(
        reporter=CapturingReporter(),
        outputs={
            WSL_QUERY: (0, "3.14.6\n"),
            ("python", "-c", prerequisites.PYTHON_VERSION_CODE): (9009, ""),
        },
    )

    with mock.patch.object(prerequisites, "_add_to_process_path"):
        _run(runner, tmp_home=tmp_path)

    assert [WINDOWS_UV, *UV_PYTHON_INSTALL_ARGS] in runner.commands
    path_scripts = [command[-1] for command in runner.commands if command[0] == "powershell"]
    assert any(str(tmp_path / ".local" / "bin").replace("/", "\\") in s for s in path_scripts)


def test_windows_names_the_store_alias_when_it_exists(tmp_path: Path) -> None:
    alias = tmp_path / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "python.exe"
    alias.parent.mkdir(parents=True)
    alias.write_text("", encoding="utf-8")
    runner = WindowsRunner(reporter=CapturingReporter(), outputs={WSL_QUERY: (0, "3.14.6\n")})
    runner.which = lambda command: WINDOWS_UV if command == "uv" else None  # type: ignore[method-assign]

    with mock.patch.object(prerequisites, "_add_to_process_path"):
        _run(runner, tmp_home=tmp_path)

    assert any(
        level == "step" and "App execution aliases" in message
        for level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )


def test_platforms_other_than_windows_install_on_the_host() -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    platform = replace(
        _windows_platform(), os=OperatingSystem.LINUX, package_manager=PackageManager.APT
    )

    with mock.patch.object(prerequisites, "is_running_in_wsl", return_value=False):
        ensure_python(runner, platform)

    assert runner.commands[-1] == ["sh", "-c", UV + shlex.join(UV_PYTHON_INSTALL_ARGS)]


def test_windows_names_an_older_python_that_stays_on_path(tmp_path: Path) -> None:
    runner = WindowsRunner(
        reporter=CapturingReporter(),
        outputs={
            WSL_QUERY: (0, "3.14.6\n"),
            ("python", "-c", prerequisites.PYTHON_VERSION_CODE): (0, "3.12.3\n"),
        },
    )

    with mock.patch.object(prerequisites, "_add_to_process_path"):
        _run(runner, tmp_home=tmp_path)

    assert [WINDOWS_UV, *UV_PYTHON_INSTALL_ARGS] in runner.commands
    assert any(
        level == "warn" and "Python 3.12.3" in message
        for level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )
