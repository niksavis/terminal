"""Tests for prerequisite checking and installation helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo, detect_os
from terminal_setup.prerequisites import (
    PrerequisiteStatus,
    check_all,
    check_command,
    check_package_manager,
    check_wsl,
    ensure_host_cli_extras,
    ensure_wsl_tools,
)
from terminal_setup.runner import Runner


def make_platform(os: OperatingSystem, package_manager: PackageManager) -> PlatformInfo:
    """Build a PlatformInfo for testing."""
    return PlatformInfo(
        os=os,
        package_manager=package_manager,
        is_wsl_available=False,
        is_wsl_default_ubuntu=False,
        wsl_distribution="Ubuntu" if os == OperatingSystem.WINDOWS else None,
        shell="/bin/zsh",
        home=Path.home(),
        wezterm_config_dir=Path.home() / ".config" / "wezterm",
        vscode_settings_path=None,
    )


class SpyRunner:
    """Lightweight runner that records commands for package-install assertions."""

    def __init__(self) -> None:
        """Initialize the recorded command list."""
        self.commands: list[list[str]] = []

    def run(  # noqa: PLR0913
        self,
        command: list[str],
        *,
        check: bool = True,
        dry_run_safe: bool = False,
        interactive: bool = False,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Record a command and return a successful completed process."""
        del check, dry_run_safe, interactive, cwd, env
        self.commands.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")


def _installed_packages(commands: list[list[str]], manager: PackageManager) -> list[str]:
    """Extract package names from install commands for a specific package manager."""
    packages: list[str] = []
    for command in commands:
        if manager == PackageManager.APT and command[:4] == ["sudo", "apt-get", "install", "-y"]:
            packages.append(command[4])
        if manager == PackageManager.HOMEBREW and command[:2] == ["brew", "install"]:
            packages.append(command[2])
        if manager == PackageManager.PACMAN and command[:4] == [
            "sudo",
            "pacman",
            "-S",
            "--noconfirm",
        ]:
            packages.append(command[4])
        if manager == PackageManager.DNF and command[:4] == ["sudo", "dnf", "install", "-y"]:
            packages.append(command[4])
    return packages


def test_check_command_finds_existing_command() -> None:
    """check_command must report present for a command that exists on PATH."""
    runner = Runner(dry_run=True)
    status = check_command(runner, "python", "python")
    assert status.present is True
    assert "python" in status.message


def test_check_command_missing_command() -> None:
    """check_command must report missing for a non-existent command."""
    runner = Runner(dry_run=True)
    status = check_command(runner, "not-a-real-tool", "not-a-real-tool-xyz")
    assert status.present is False


def test_check_package_manager_unknown() -> None:
    """check_package_manager must report missing when no manager is found."""
    platform = make_platform(OperatingSystem.LINUX, PackageManager.UNKNOWN)
    status = check_package_manager(platform)
    assert status.present is False


def test_check_package_manager_known() -> None:
    """check_package_manager must report present for a known manager."""
    platform = make_platform(OperatingSystem.LINUX, PackageManager.APT)
    status = check_package_manager(platform)
    assert status.present is True


def test_check_wsl_not_required_on_linux() -> None:
    """WSL checks must pass on Linux because it is not required."""
    platform = make_platform(OperatingSystem.LINUX, PackageManager.APT)
    runner = Runner(dry_run=True)
    status = check_wsl(platform, runner)
    assert status.present is True


def test_check_wsl_missing_on_windows() -> None:
    """WSL checks must fail on Windows when WSL is unavailable."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = Runner(dry_run=True)
    status = check_wsl(platform, runner)
    assert status.present is False


def test_check_all_returns_list() -> None:
    """check_all must return a list of PrerequisiteStatus objects."""
    platform = make_platform(detect_os(), PackageManager.UNKNOWN)
    runner = Runner(dry_run=True)
    statuses = check_all(platform, runner)
    assert all(isinstance(s, PrerequisiteStatus) for s in statuses)


def test_ensure_wsl_tools_installs_agent_first_baseline() -> None:
    """WSL tool install script should include the curated agent-first package set."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = SpyRunner()

    ensure_wsl_tools(runner, platform)

    assert len(runner.commands) == 1
    command = runner.commands[0]
    assert command[:5] == ["wsl", "-d", "Ubuntu", "--", "sh"]
    script = command[-1]
    for package in [
        "fzf",
        "fd-find",
        "bat",
        "ripgrep",
        "jq",
        "yq",
        "shellcheck",
        "tree",
        "xh",
        "ast-grep",
        "sd",
        "git-delta",
        "typos",
        "uv",
    ]:
        assert package in script
    for removed in ["eza", "zoxide", "micro", "htop"]:
        assert removed not in script


def test_ensure_host_cli_extras_uses_agent_first_baseline_per_manager() -> None:
    """Host extras should install the same baseline with package-name mapping per manager."""
    expected = {
        PackageManager.APT: [
            "fzf",
            "fd-find",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "xh",
            "ast-grep",
            "sd",
            "git-delta",
            "typos",
            "uv",
        ],
        PackageManager.HOMEBREW: [
            "fzf",
            "fd",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "xh",
            "ast-grep",
            "sd",
            "git-delta",
            "typos-cli",
            "uv",
        ],
        PackageManager.PACMAN: [
            "fzf",
            "fd",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "xh",
            "ast-grep",
            "sd",
            "git-delta",
            "typos",
            "uv",
        ],
        PackageManager.DNF: [
            "fzf",
            "fd-find",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "xh",
            "ast-grep",
            "sd",
            "git-delta",
            "typos",
            "uv",
        ],
    }

    for manager, expected_packages in expected.items():
        platform = make_platform(OperatingSystem.LINUX, manager)
        runner = SpyRunner()

        ensure_host_cli_extras(runner, platform)

        assert _installed_packages(runner.commands, manager) == expected_packages


def test_ensure_host_cli_extras_noop_on_windows() -> None:
    """Windows host path should skip host extra package installation."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = SpyRunner()

    ensure_host_cli_extras(runner, platform)

    assert runner.commands == []
