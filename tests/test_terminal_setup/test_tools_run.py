from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest import mock

import pytest

from terminal_setup import cli
from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo
from terminal_setup.runner import Runner

from .test_runner import CapturingReporter

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the probe runs in a POSIX sh")


def _tool(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def bare_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    if shutil.which("sh") is None or shutil.which("head") is None:
        pytest.skip("needs a POSIX shell")
    system = tmp_path / "system"
    system.mkdir()
    for name in ("sh", "head"):
        (system / name).symlink_to(str(shutil.which(name)))
    local = tmp_path / "home" / ".local" / "bin"
    local.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", str(system))
    return local


def _linux() -> PlatformInfo:
    return PlatformInfo(
        os=OperatingSystem.LINUX,
        package_manager=PackageManager.APT,
        is_wsl_available=False,
        is_wsl_default_debian_family=False,
        wsl_distribution=None,
        shell="/bin/zsh",
        home=Path.home(),
        wezterm_config_dir=None,
        vscode_settings_path=None,
    )


def _verify(*, no_sudo: bool) -> Runner:
    runner = Runner(reporter=CapturingReporter())
    with mock.patch.object(cli, "is_running_in_wsl", return_value=False):
        cli.verify_tools_run(
            runner,
            _linux(),
            include_starship=False,
            selected_agents=[],
            herdr=False,
            no_sudo=no_sudo,
        )
    return runner


def test_a_tool_that_cannot_start_is_a_failed_step(bare_home: Path) -> None:
    _tool(
        bare_home,
        "node",
        "echo 'node: error while loading shared libraries: libatomic.so.1' >&2; exit 127",
    )
    _tool(bare_home, "uv", "echo 'uv 0.13.9'")

    runner = _verify(no_sudo=True)

    assert runner.failures == ["run host:node"]
    assert any(
        level == "warn" and "libatomic.so.1" in message
        for level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )


def test_a_missing_tool_is_a_failed_step_when_setup_installs_it(bare_home: Path) -> None:
    _tool(bare_home, "uv", "echo 'uv 0.13.9'")

    runner = _verify(no_sudo=False)

    assert "run host:node" in runner.failures
    assert "run host:uv" not in runner.failures


def test_a_tool_that_runs_is_reported_with_its_version(bare_home: Path) -> None:
    _tool(bare_home, "node", "echo v26.13.1")

    runner = _verify(no_sudo=True)

    assert runner.failures == []
    assert ("success", "host:node runs (v26.13.1)") in runner.reporter.messages  # type: ignore[attr-defined]
