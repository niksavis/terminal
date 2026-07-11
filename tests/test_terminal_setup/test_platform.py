"""Tests for platform detection."""

from __future__ import annotations

from terminal_setup.platform import (
    OperatingSystem,
    PackageManager,
    detect_os,
    detect_package_manager,
    get_home_directory,
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
