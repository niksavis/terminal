"""Tests for configuration deployment."""

from __future__ import annotations

import json
from pathlib import Path

from terminal_setup.configs import (
    CHEAT_SHEET_PATH,
    TEMPLATE_DIR,
    configure_vscode_terminal,
    deploy_micro_config,
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
    for name in ["wezterm.lua", "tmux.conf", "zshrc", "starship.toml", "micro-settings.json"]:
        assert template_path(name).exists(), f"template {name} is missing"


def test_template_dir_exists() -> None:
    """TEMPLATE_DIR must exist and contain templates."""
    assert TEMPLATE_DIR.is_dir()
    assert len(list(TEMPLATE_DIR.iterdir())) >= 5


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
    content = destination.read_text(encoding="utf-8")
    assert "WezTerm" in content
    assert "__WSL_START_DIR__" not in content


def test_deploy_wezterm_config_supports_optional_wsl_start_dir(tmp_path: Path) -> None:
    """Optional install input should be rendered into the deployed WezTerm config."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    deploy_wezterm_config(runner, platform, wsl_start_dir="$HOME/workspace")

    assert platform.wezterm_config_dir is not None
    destination = platform.wezterm_config_dir / "wezterm.lua"
    content = destination.read_text(encoding="utf-8")
    assert "$HOME/workspace" in content
    assert "__WSL_START_DIR__" not in content


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


def test_deploy_micro_config(tmp_path: Path) -> None:
    """deploy_micro_config must copy micro settings to ~/.config/micro/settings.json."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_micro_config(runner, platform)

    destination = tmp_path / ".config" / "micro" / "settings.json"
    assert destination.exists()
    content = destination.read_text(encoding="utf-8")
    expected = template_path("micro-settings.json").read_text(encoding="utf-8")
    assert content == expected


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
    assert profiles["Ubuntu (WSL)"]["args"] == ["-d", "Ubuntu"]


def test_configure_vscode_terminal_windows_uses_detected_distro(tmp_path: Path) -> None:
    """Windows profile should follow the detected WSL distro name."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    platform = PlatformInfo(
        os=platform.os,
        package_manager=platform.package_manager,
        is_wsl_available=platform.is_wsl_available,
        is_wsl_default_ubuntu=platform.is_wsl_default_ubuntu,
        wsl_distribution="Ubuntu-24.04",
        shell=platform.shell,
        home=platform.home,
        wezterm_config_dir=platform.wezterm_config_dir,
        vscode_settings_path=platform.vscode_settings_path,
    )
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.defaultProfile.windows") == "Ubuntu-24.04 (WSL)"
    profiles = settings.get("terminal.integrated.profiles.windows", {})
    assert "Ubuntu-24.04 (WSL)" in profiles
    assert profiles["Ubuntu-24.04 (WSL)"]["args"] == ["-d", "Ubuntu-24.04"]
    assert "Ubuntu (WSL)" not in profiles


def test_configure_vscode_terminal_windows_removes_stale_ubuntu_profile(tmp_path: Path) -> None:
    """Stale Ubuntu profile should be removed when detected distro is Ubuntu-24.04."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    platform = PlatformInfo(
        os=platform.os,
        package_manager=platform.package_manager,
        is_wsl_available=platform.is_wsl_available,
        is_wsl_default_ubuntu=platform.is_wsl_default_ubuntu,
        wsl_distribution="Ubuntu-24.04",
        shell=platform.shell,
        home=platform.home,
        wezterm_config_dir=platform.wezterm_config_dir,
        vscode_settings_path=platform.vscode_settings_path,
    )
    assert platform.vscode_settings_path is not None
    stale = {
        "terminal.integrated.profiles.windows": {
            "WSL (Default)": {
                "path": "C:\\Windows\\System32\\wsl.exe",
                "icon": "terminal-ubuntu",
            },
            "Ubuntu (WSL)": {
                "path": "C:\\Windows\\System32\\wsl.exe",
                "args": ["-d", "Ubuntu"],
                "icon": "terminal-ubuntu",
            },
        }
    }
    platform.vscode_settings_path.write_text(json.dumps(stale, indent=2) + "\n", encoding="utf-8")

    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    profiles = settings.get("terminal.integrated.profiles.windows", {})
    assert "WSL (Default)" not in profiles
    assert "Ubuntu (WSL)" not in profiles
    assert "Ubuntu-24.04 (WSL)" in profiles


def test_configure_vscode_terminal_windows_sets_optional_cwd(tmp_path: Path) -> None:
    """Windows settings should use an optional user-provided cwd when provided."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform, windows_terminal_cwd="D:\\Workspace")

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.cwd") == "D:\\Workspace"


def test_configure_vscode_terminal_windows_preserves_existing_cwd_when_unset(
    tmp_path: Path,
) -> None:
    """Without optional input, custom user cwd should be preserved."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    assert platform.vscode_settings_path is not None
    platform.vscode_settings_path.write_text(
        json.dumps({"terminal.integrated.cwd": "E:\\Workspace"}, indent=2) + "\n",
        encoding="utf-8",
    )

    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.cwd") == "E:\\Workspace"


def test_configure_vscode_terminal_windows_removes_stale_existing_cwd_when_unset(
    tmp_path: Path,
) -> None:
    """Without optional input, stale hardcoded cwd from older versions should be removed."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    assert platform.vscode_settings_path is not None
    platform.vscode_settings_path.write_text(
        json.dumps({"terminal.integrated.cwd": "D:\\Development"}, indent=2) + "\n",
        encoding="utf-8",
    )

    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert "terminal.integrated.cwd" not in settings


def test_configure_vscode_terminal_windows_uses_optional_wsl_cwd(tmp_path: Path) -> None:
    """WSL profile cwd should respect optional install input."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform, wsl_terminal_cwd="$HOME/workspace")

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    profiles = settings.get("terminal.integrated.profiles.windows", {})
    assert profiles["Ubuntu (WSL)"]["args"] == ["-d", "Ubuntu", "--cd", "$HOME/workspace"]
