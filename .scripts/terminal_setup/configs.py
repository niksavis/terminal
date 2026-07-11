"""Configuration file deployment for WezTerm, tmux, zsh, starship, and docs."""

from __future__ import annotations

import json
from pathlib import Path

from .platform import OperatingSystem, PlatformInfo
from .runner import Runner

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = _REPO_ROOT / ".scripts" / "terminal_setup" / "templates"
CHEAT_SHEET_PATH = _REPO_ROOT / "terminal-cheat-sheet.html"


def template_path(name: str) -> Path:
    """Return the path to a named template file."""
    return TEMPLATE_DIR / name


def deploy_wezterm_config(runner: Runner, platform: PlatformInfo) -> None:
    """Deploy the WezTerm configuration file."""
    if platform.wezterm_config_dir is None:
        return
    runner.ensure_dir(platform.wezterm_config_dir)
    source = template_path("wezterm.lua")
    destination = platform.wezterm_config_dir / "wezterm.lua"
    runner.copy(source, destination)


def deploy_tmux_config(runner: Runner, platform: PlatformInfo) -> None:
    """Deploy the tmux configuration file."""
    destination = platform.home / ".tmux.conf"
    runner.copy(template_path("tmux.conf"), destination)


def deploy_zsh_config(runner: Runner, platform: PlatformInfo) -> None:
    """Deploy the zsh configuration file."""
    destination = platform.home / ".zshrc"
    runner.copy(template_path("zshrc"), destination)


def deploy_starship_config(runner: Runner, platform: PlatformInfo) -> None:
    """Deploy the starship configuration file."""
    config_dir = platform.home / ".config"
    runner.ensure_dir(config_dir)
    destination = config_dir / "starship.toml"
    runner.copy(template_path("starship.toml"), destination)


def deploy_cheat_sheet(runner: Runner, platform: PlatformInfo) -> None:
    """Deploy the terminal cheat sheet to the home directory."""
    if not CHEAT_SHEET_PATH.exists():
        runner.reporter.warn(f"cheat sheet not found at {CHEAT_SHEET_PATH}")
        return
    destination = platform.home / "terminal-cheat-sheet.html"
    runner.copy(CHEAT_SHEET_PATH, destination)


def _wsl_distro(platform: PlatformInfo) -> str:
    """Return the WSL distribution to use, falling back to Ubuntu."""
    return platform.wsl_distribution or "Ubuntu"


def set_wsl_default_shell(
    runner: Runner, platform: PlatformInfo, shell: str = "/usr/bin/zsh"
) -> None:
    """Set the default shell inside WSL Ubuntu."""
    distro = _wsl_distro(platform)
    runner.run(["wsl", "-d", distro, "--", "chsh", "-s", shell])


def set_host_default_shell(runner: Runner, platform: PlatformInfo, shell: str = "zsh") -> None:
    """Set the default login shell on the host."""
    if platform.os == OperatingSystem.WINDOWS:
        return
    shell_path = runner.which(shell)
    if shell_path is None:
        return
    runner.run(["chsh", "-s", shell_path])


def deploy_all(
    runner: Runner,
    platform: PlatformInfo,
    *,
    include_starship: bool = True,
) -> None:
    """Deploy all configuration files and set the default shell."""
    deploy_wezterm_config(runner, platform)
    deploy_cheat_sheet(runner, platform)
    if platform.os == OperatingSystem.WINDOWS:
        deploy_wsl_configs(runner, platform)
        set_wsl_default_shell(runner, platform)
    else:
        deploy_tmux_config(runner, platform)
        deploy_zsh_config(runner, platform)
        if include_starship:
            deploy_starship_config(runner, platform)
        set_host_default_shell(runner, platform)


def deploy_wsl_configs(runner: Runner, platform: PlatformInfo) -> None:
    """Copy host config templates into the WSL Ubuntu home directory."""
    distro = _wsl_distro(platform)
    username = platform.home.name or "user"
    wsl_home = f"/home/{username}"
    for template, target_name in [
        ("tmux.conf", ".tmux.conf"),
        ("zshrc", ".zshrc"),
        ("starship.toml", ".config/starship.toml"),
    ]:
        source = template_path(template)
        destination = f"{wsl_home}/{target_name}"
        runner.run(["wsl", "-d", distro, "--", "mkdir", "-p", destination.rsplit("/", 1)[0]])
        runner.run(["wsl", "-d", distro, "--", "cp", str(source), destination])
    if CHEAT_SHEET_PATH.exists():
        cheat_destination = f"{wsl_home}/terminal-cheat-sheet.html"
        runner.run(["wsl", "-d", distro, "--", "cp", str(CHEAT_SHEET_PATH), cheat_destination])


def configure_vscode_terminal(runner: Runner, platform: PlatformInfo) -> None:
    """Update VS Code settings to use the configured terminal."""
    if platform.vscode_settings_path is None:
        return
    settings_path = platform.vscode_settings_path
    settings: dict[str, object] = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}

    if platform.os == OperatingSystem.WINDOWS:
        settings["terminal.integrated.defaultProfile.windows"] = "Ubuntu (WSL)"
        settings["terminal.integrated.profiles.windows"] = {
            "Ubuntu (WSL)": {
                "path": "C:\\Windows\\System32\\wsl.exe",
                "args": ["-d", "Ubuntu"],
                "icon": "terminal-ubuntu",
            }
        }
    elif platform.os == OperatingSystem.LINUX:
        settings["terminal.integrated.defaultProfile.linux"] = "zsh"
    elif platform.os == OperatingSystem.MACOS:
        settings["terminal.integrated.defaultProfile.osx"] = "zsh"

    runner.ensure_dir(settings_path.parent)
    runner.write_text(settings_path, json.dumps(settings, indent=2) + "\n")


def ensure_vscode_extension(runner: Runner, extension_id: str) -> None:
    """Install a VS Code extension if code is available."""
    if runner.which("code") is None:
        return
    runner.run(["code", "--install-extension", extension_id])


def install_vscode_wsl_extension(runner: Runner, platform: PlatformInfo) -> None:
    """Install the VS Code Remote - WSL extension on Windows."""
    if platform.os != OperatingSystem.WINDOWS:
        return
    ensure_vscode_extension(runner, "ms-vscode-remote.remote-wsl")
