"""Coverage for the verification-report probes and generated install scripts."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast
from unittest import mock

import pytest

from terminal_setup.cli import _wsl_command_present, _wsl_file_exists
from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo
from terminal_setup.prerequisites import (
    _ensure_starship_user_install,
    _ensure_wezterm_appimage,
)
from terminal_setup.runner import ConsoleReporter, Runner


def make_platform(os: OperatingSystem, home: Path) -> PlatformInfo:
    """Build a PlatformInfo for testing."""
    return PlatformInfo(
        os=os,
        package_manager=PackageManager.UNKNOWN,
        is_wsl_available=False,
        is_wsl_default_ubuntu=False,
        wsl_distribution="Ubuntu" if os == OperatingSystem.WINDOWS else None,
        shell="/bin/zsh",
        home=home,
        wezterm_config_dir=home / ".config" / "wezterm",
        vscode_settings_path=None,
    )


class ScriptedRunner:
    """Runner double returning canned results per matched substring."""

    def __init__(self, responses: dict[str, subprocess.CompletedProcess[str]]) -> None:
        """Store canned responses keyed by a script substring."""
        self.responses = responses
        self.commands: list[list[str]] = []
        self.dry_run = False
        self.reporter = ConsoleReporter()

    def run(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        """Return the canned response whose key appears in the script."""
        self.commands.append(command)
        script = command[-1]
        for key, response in self.responses.items():
            if key in script:
                return response
        return subprocess.CompletedProcess(command, 0, "", "")

    def which(self, _command: str) -> str | None:
        """No commands on PATH by default."""
        return None

    def ensure_dir(self, _path: Path) -> None:
        """No-op directory creation."""


def test_wsl_command_present_prefers_user_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """The report must show the ~/.local/bin copy when both copies exist."""
    monkeypatch.setattr("terminal_setup.cli.is_running_in_wsl", lambda: True)
    runner = ScriptedRunner({
        "~/.local/bin/fzf": subprocess.CompletedProcess([], 0, "~/.local/bin/fzf\n", "")
    })
    platform = make_platform(OperatingSystem.LINUX, Path("/home/user"))
    ok, detail = _wsl_command_present(cast(Runner, runner), platform, "fzf")
    assert ok
    assert detail == "~/.local/bin/fzf"


def test_wsl_command_present_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty probe result must report the command as missing."""
    monkeypatch.setattr("terminal_setup.cli.is_running_in_wsl", lambda: True)
    runner = ScriptedRunner({"": subprocess.CompletedProcess([], 1, "", "")})
    platform = make_platform(OperatingSystem.LINUX, Path("/home/user"))
    ok, detail = _wsl_command_present(cast(Runner, runner), platform, "nope")
    assert not ok
    assert detail == ""


def test_wsl_file_exists_maps_return_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """File probes must map the shell exit code to a boolean."""
    monkeypatch.setattr("terminal_setup.cli.is_running_in_wsl", lambda: True)
    platform = make_platform(OperatingSystem.LINUX, Path("/home/user"))
    present = ScriptedRunner({"test -f": subprocess.CompletedProcess([], 0, "", "")})
    ok, _ = _wsl_file_exists(cast(Runner, present), platform, "~/.zshrc")
    assert ok
    absent = ScriptedRunner({"test -f": subprocess.CompletedProcess([], 1, "", "")})
    ok, _ = _wsl_file_exists(cast(Runner, absent), platform, "~/.zshrc")
    assert not ok


def test_runner_dry_run_safe_commands_execute_for_real(tmp_path: Path) -> None:
    """dry_run_safe probes must run even in dry-run so reports reflect reality."""
    marker = tmp_path / "ran"
    runner = Runner(dry_run=True, reporter=ConsoleReporter())
    # Feed sh a POSIX path: a Windows backslash path is mangled by the shell.
    runner.run(["sh", "-c", f"touch {marker.as_posix()}"], dry_run_safe=True)
    assert marker.exists()


def test_runner_check_false_propagates_return_code() -> None:
    """check=False must surface the child's exit code instead of raising."""
    runner = Runner(dry_run=False, reporter=ConsoleReporter())
    result = runner.run(["sh", "-c", "exit 7"], check=False)
    assert result.returncode == 7


def test_console_reporter_confirm_returns_false_on_eof() -> None:
    """A closed stdin (headless run) must answer no instead of crashing."""
    reporter = ConsoleReporter()
    with mock.patch("builtins.input", side_effect=EOFError):
        assert reporter.confirm("proceed?") is False


def test_wezterm_appimage_script_verifies_checksum() -> None:
    """The AppImage installer must pin the download to its published sha256."""
    runner = ScriptedRunner({})
    _ensure_wezterm_appimage(cast(Runner, runner))
    scripts = [command[-1] for command in runner.commands]
    assert any("sha256" in script.lower() for script in scripts), scripts


def test_starship_windows_script_verifies_checksum(tmp_path: Path) -> None:
    """The Windows starship installer must verify the archive hash."""
    runner = ScriptedRunner({})
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    _ensure_starship_user_install(cast(Runner, runner), platform)
    scripts = [command[-1] for command in runner.commands if command[0] == "powershell"]
    assert scripts
    assert any("Get-FileHash" in script for script in scripts)
