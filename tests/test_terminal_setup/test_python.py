from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

from terminal_setup import prerequisites
from terminal_setup.platform import OperatingSystem, PackageManager, wsl_exec_command
from terminal_setup.prerequisites import (
    PYTHON_INSTALLED_QUERY,
    UV_PYTHON_INSTALL_ARGS,
    UV_PYTHON_LIST_ARGS,
    UV_PYTHON_MANAGED_ARGS,
    UV_PYTHON_UPGRADE_ARGS,
    ensure_python,
    newer_python_patch,
    python_meets_target,
)

from .test_runner import CapturingReporter
from .test_unattended import RecordingRunner, _windows_platform

UV = 'PATH="$HOME/.local/bin:$PATH"; uv '
WSL_QUERY = tuple(wsl_exec_command("Ubuntu", ["sh", "-c", PYTHON_INSTALLED_QUERY]))
WSL_MANAGED = tuple(
    wsl_exec_command("Ubuntu", ["sh", "-c", UV + shlex.join(UV_PYTHON_MANAGED_ARGS)])
)
WSL_LIST = tuple(wsl_exec_command("Ubuntu", ["sh", "-c", UV + shlex.join(UV_PYTHON_LIST_ARGS)]))
WSL_INSTALL = wsl_exec_command("Ubuntu", ["sh", "-c", UV + shlex.join(UV_PYTHON_INSTALL_ARGS)])
WSL_UPGRADE = wsl_exec_command("Ubuntu", ["sh", "-c", UV + shlex.join(UV_PYTHON_UPGRADE_ARGS)])
WINDOWS_UV = "C:/uv/uv.exe"


def _listing(*entries: tuple[str, str | None], implementation: str = "cpython") -> str:
    return json.dumps([
        {"implementation": implementation, "variant": "default", "version": v, "path": p}
        for v, p in entries
    ])


CURRENT_LISTING = _listing(("3.14.8", "/uv/cpython-3.14.8/bin/python3.14"))
NEWER_LISTING = _listing(("3.14.9", None), ("3.14.8", "/uv/cpython-3.14.8/bin/python3.14"))


@pytest.mark.parametrize(
    ("version", "expected"),
    [(None, False), ("3.12.3", False), ("3.13.9", False), ("3.14.0", True), ("3.15.1", True)],
)
def test_python_meets_target(version: str | None, *, expected: bool) -> None:
    assert python_meets_target(version) is expected


MACHINE_PYTHON = "C:/Program Files/Python314/python.exe"


class WindowsRunner(RecordingRunner):
    python_path: str = MACHINE_PYTHON

    def which(self, command: str) -> str | None:
        return {"uv": WINDOWS_UV, "python": self.python_path}.get(command)


def _windows_runner(python: str, version: tuple[int, str]) -> WindowsRunner:
    runner = WindowsRunner(
        reporter=CapturingReporter(),
        outputs={
            WSL_QUERY: (0, "3.14.6\n"),
            (python, "-c", prerequisites.PYTHON_VERSION_CODE): version,
        },
    )
    runner.python_path = python
    return runner


def _user_python(home: Path) -> str:
    return str(home / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe")


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
        outputs={
            WSL_QUERY: (0, "3.14.6\n"),
            WSL_MANAGED: (managed, ""),
            WSL_LIST: (0, NEWER_LISTING),
        },
    )

    _run(runner, update=True)

    assert (WSL_UPGRADE in runner.commands) is upgraded
    assert WSL_INSTALL not in runner.commands


def test_windows_without_uv_records_a_failed_step() -> None:
    runner = RecordingRunner(reporter=CapturingReporter(), outputs={WSL_QUERY: (0, "3.14.6\n")})

    _run(runner)

    assert runner.failures == ["install Python on Windows"]


@pytest.mark.parametrize(
    ("version", "level", "text"),
    [
        ((0, "3.14.7\n"), "info", "managed by your organisation"),
        ((0, "3.12.3\n"), "warn", "Software Center"),
    ],
)
def test_windows_only_advises_on_a_machine_wide_python(
    tmp_path: Path, version: tuple[int, str], level: str, text: str
) -> None:
    runner = _windows_runner(MACHINE_PYTHON, version)

    _run(runner, update=True, tmp_home=tmp_path)

    assert not [command for command in runner.commands if command[:2] == [WINDOWS_UV, "python"]]
    assert runner.failures == []
    assert any(
        found_level == level and text in message and MACHINE_PYTHON in message
        for found_level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )


def test_windows_skips_a_present_user_python(tmp_path: Path) -> None:
    runner = _windows_runner(_user_python(tmp_path), (0, "3.14.7\n"))

    _run(runner, tmp_home=tmp_path)

    assert [WINDOWS_UV, *UV_PYTHON_INSTALL_ARGS] not in runner.commands
    assert runner.failures == []


def test_windows_installs_python_and_adds_the_bin_dir(tmp_path: Path) -> None:
    alias = str(tmp_path / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "python.exe")
    runner = _windows_runner(alias, (9009, ""))

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


def test_windows_names_an_older_user_python_that_stays_on_path(tmp_path: Path) -> None:
    runner = _windows_runner(_user_python(tmp_path), (0, "3.12.3\n"))

    with mock.patch.object(prerequisites, "_add_to_process_path"):
        _run(runner, tmp_home=tmp_path)

    assert [WINDOWS_UV, *UV_PYTHON_INSTALL_ARGS] in runner.commands
    assert any(
        level == "warn" and "Python 3.12.3" in message
        for level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )


def test_update_relinks_python_and_python3_to_the_new_patch() -> None:
    assert UV_PYTHON_UPGRADE_ARGS[: len(UV_PYTHON_INSTALL_ARGS)] == UV_PYTHON_INSTALL_ARGS
    assert UV_PYTHON_UPGRADE_ARGS[-1] == "--upgrade"
    assert "--default" in UV_PYTHON_UPGRADE_ARGS


@pytest.mark.parametrize(
    ("listing", "expected"),
    [
        (CURRENT_LISTING, None),
        (NEWER_LISTING, "3.14.9"),
        (_listing(("3.14.9", None)), "3.14.9"),
        (_listing(("3.14.7", None), ("3.14.8", "/uv/python")), None),
        (
            CURRENT_LISTING[:-1] + ", " + _listing(("3.14.9", None), implementation="graalpy")[1:],
            None,
        ),
    ],
)
def test_newer_python_patch_compares_cpython_downloads_with_installs(
    listing: str, expected: str | None
) -> None:
    assert newer_python_patch(listing) == expected


class OrderedRunner(RecordingRunner):
    def run(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.reporter.messages.append(("run", " ".join(command)))  # type: ignore[attr-defined]
        return super().run(command, **kwargs)  # type: ignore[arg-type]


def _wsl_update(listing: tuple[int, str]) -> OrderedRunner:
    runner = OrderedRunner(
        reporter=CapturingReporter(),
        outputs={WSL_QUERY: (0, "3.14.8\n"), WSL_MANAGED: (0, ""), WSL_LIST: listing},
    )
    _run(runner, update=True)
    return runner


def test_wsl_update_skips_the_upgrade_when_the_patch_is_current() -> None:
    runner = _wsl_update((0, CURRENT_LISTING))

    assert WSL_UPGRADE not in runner.commands
    assert not [m for _, m in runner.reporter.messages if "sessions" in m]  # type: ignore[attr-defined]


@pytest.mark.parametrize("listing", [(0, NEWER_LISTING), (2, ""), (0, "not json")])
def test_wsl_update_warns_about_running_sessions_before_the_upgrade(
    listing: tuple[int, str],
) -> None:
    runner = _wsl_update(listing)

    messages = runner.reporter.messages  # type: ignore[attr-defined]
    warning = next(
        i for i, (level, m) in enumerate(messages) if level == "warn" and "sessions" in m
    )
    upgrade = messages.index(("run", " ".join(WSL_UPGRADE)))
    assert warning < upgrade


@pytest.mark.parametrize(("listing", "upgraded"), [(CURRENT_LISTING, False), (NEWER_LISTING, True)])
def test_windows_update_upgrades_a_user_python_only_for_a_newer_patch(
    tmp_path: Path, listing: str, *, upgraded: bool
) -> None:
    runner = _windows_runner(_user_python(tmp_path), (0, "3.14.8\n"))
    runner.outputs[(WINDOWS_UV, *UV_PYTHON_MANAGED_ARGS)] = (0, "")
    runner.outputs[(WINDOWS_UV, *UV_PYTHON_LIST_ARGS)] = (0, listing)
    runner.outputs[WSL_MANAGED] = (2, "")

    _run(runner, update=True, tmp_home=tmp_path)

    assert ([WINDOWS_UV, *UV_PYTHON_UPGRADE_ARGS] in runner.commands) is upgraded
