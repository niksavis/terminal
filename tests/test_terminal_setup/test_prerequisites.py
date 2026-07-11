"""Tests for prerequisite checking and installation helpers."""

from __future__ import annotations

from pathlib import Path

from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo, detect_os
from terminal_setup.prerequisites import (
    PrerequisiteStatus,
    check_all,
    check_command,
    check_package_manager,
    check_wsl,
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
