"""Tests for platform detection."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from terminal_setup.platform import (
    OperatingSystem,
    PackageManager,
    detect_os,
    detect_package_manager,
    get_home_directory,
    get_vscode_settings_path,
    is_running_in_wsl,
)


def test_detect_os_returns_known_value() -> None:
    """detect_os must return a known operating system enum."""
    os = detect_os()
    assert os in OperatingSystem


def test_detect_package_manager_matches_os() -> None:
    """detect_package_manager must return a package manager compatible with the OS."""
    os = detect_os()
    manager = detect_package_manager(os)
    assert manager in PackageManager


def test_home_directory_exists() -> None:
    """get_home_directory must return an existing directory."""
    home = get_home_directory()
    assert home.exists()
    assert home.is_dir()


def test_is_running_in_wsl_true_for_microsoft_kernel() -> None:
    """is_running_in_wsl must return True when the kernel release contains 'microsoft'."""
    with (
        mock.patch("terminal_setup.platform.detect_os", return_value=OperatingSystem.LINUX),
        mock.patch(
            "pathlib.Path.read_text",
            return_value="5.15.146.1-microsoft-standard-WSL2",
        ),
    ):
        assert is_running_in_wsl() is True


def test_is_running_in_wsl_false_on_non_linux() -> None:
    """is_running_in_wsl must return False on non-Linux platforms."""
    with mock.patch("terminal_setup.platform.detect_os", return_value=OperatingSystem.WINDOWS):
        assert is_running_in_wsl() is False


def test_is_running_in_wsl_false_for_plain_linux() -> None:
    """is_running_in_wsl must return False for a non-WSL Linux kernel."""
    with (
        mock.patch("terminal_setup.platform.detect_os", return_value=OperatingSystem.LINUX),
        mock.patch("pathlib.Path.read_text", return_value="6.8.0-35-generic"),
    ):
        assert is_running_in_wsl() is False


def test_vscode_settings_fallback_is_a_real_user_settings_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On a fresh machine the fallback must be a path VS Code actually reads."""
    monkeypatch.setattr("terminal_setup.platform.get_home_directory", lambda: tmp_path)
    monkeypatch.setattr("terminal_setup.platform.detect_os", lambda: OperatingSystem.LINUX)
    path = get_vscode_settings_path()
    assert path == tmp_path / ".config" / "Code" / "User" / "settings.json"

    monkeypatch.setattr("terminal_setup.platform.detect_os", lambda: OperatingSystem.WINDOWS)
    path = get_vscode_settings_path()
    assert path == tmp_path / "AppData" / "Roaming" / "Code" / "User" / "settings.json"


def test_vscode_settings_prefers_existing_location(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An existing settings.json wins over the OS default."""
    existing = tmp_path / ".config" / "Code" / "User" / "settings.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("terminal_setup.platform.get_home_directory", lambda: tmp_path)
    monkeypatch.setattr("terminal_setup.platform.detect_os", lambda: OperatingSystem.WINDOWS)
    assert get_vscode_settings_path() == existing
