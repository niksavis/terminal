"""Tests for configuration deployment."""

from __future__ import annotations

import json
from pathlib import Path

from terminal_setup.configs import (
    CHEAT_SHEET_PATH,
    TEMPLATE_DIR,
    configure_vscode_terminal,
    deploy_cheat_sheet,
    deploy_tmux_config,
    deploy_wezterm_config,
    deploy_zsh_config,
    template_path,
)
from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo
from terminal_setup.runner import Runner


def make_platform(
    os: OperatingSystem,
    home: Path,
    package_manager: PackageManager = PackageManager.UNKNOWN,
) -> PlatformInfo:
    """Build a PlatformInfo for testing."""
    return PlatformInfo(
        os=os,
        package_manager=package_manager,
        is_wsl_available=False,
        is_wsl_default_ubuntu=False,
        wsl_distribution="Ubuntu" if os == OperatingSystem.WINDOWS else None,
        shell="/bin/zsh",
        home=home,
        wezterm_config_dir=home / ".config" / "wezterm",
        vscode_settings_path=home / "settings.json",
    )


def test_template_path_points_to_existing_files() -> None:
    """All referenced templates must exist."""
    for name in ["wezterm.lua", "tmux.conf", "zshrc", "starship.toml"]:
        assert template_path(name).exists(), f"template {name} is missing"


def test_template_dir_exists() -> None:
    """TEMPLATE_DIR must exist and contain templates."""
    assert TEMPLATE_DIR.is_dir()
    assert len(list(TEMPLATE_DIR.iterdir())) >= 4


def test_cheat_sheet_exists() -> None:
    """The terminal cheat sheet must exist in the repo."""
    assert CHEAT_SHEET_PATH.exists(), "terminal-cheat-sheet.md should exist in repo root"


def test_deploy_wezterm_config(tmp_path: Path) -> None:
    """deploy_wezterm_config must copy the template to the config directory."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_wezterm_config(runner, platform)

    assert platform.wezterm_config_dir is not None
    destination = platform.wezterm_config_dir / "wezterm.lua"
    assert destination.exists()
    assert "WezTerm" in destination.read_text(encoding="utf-8")


def test_deploy_tmux_config(tmp_path: Path) -> None:
    """deploy_tmux_config must copy the tmux template to ~/.tmux.conf."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_tmux_config(runner, platform)

    destination = tmp_path / ".tmux.conf"
    assert destination.exists()
    assert "tmux" in destination.read_text(encoding="utf-8")


def test_deploy_zsh_config(tmp_path: Path) -> None:
    """deploy_zsh_config must copy the zsh template to ~/.zshrc."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_zsh_config(runner, platform)

    destination = tmp_path / ".zshrc"
    assert destination.exists()
    assert "HISTFILE" in destination.read_text(encoding="utf-8")


def test_configure_vscode_terminal_linux(tmp_path: Path) -> None:
    """configure_vscode_terminal must set the default profile on Linux."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.defaultProfile.linux") == "zsh"


def test_configure_vscode_terminal_windows(tmp_path: Path) -> None:
    """configure_vscode_terminal must set the WSL profile on Windows."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.defaultProfile.windows") == "Ubuntu (WSL)"
    profiles = settings.get("terminal.integrated.profiles.windows", {})
    assert "Ubuntu (WSL)" in profiles


def test_deploy_cheat_sheet(tmp_path: Path) -> None:
    """deploy_cheat_sheet must copy the cheat sheet to the home directory."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_cheat_sheet(runner, platform)

    destination = tmp_path / "terminal-cheat-sheet.html"
    assert destination.exists()
    assert "pwd" in destination.read_text(encoding="utf-8")
