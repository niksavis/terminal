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
    current_shell = runner.run(
        ["wsl", "-d", distro, "--", "sh", "-c", "getent passwd $(whoami) | cut -d: -f7"],
        check=False,
        dry_run_safe=True,
    ).stdout.strip()
    if current_shell == shell:
        return
    # chsh may prompt for the user's password.
    runner.run(["wsl", "-d", distro, "--", "chsh", "-s", shell], interactive=True)


def set_host_default_shell(runner: Runner, platform: PlatformInfo, shell: str = "zsh") -> None:
    """Set the default login shell on the host."""
    if platform.os == OperatingSystem.WINDOWS:
        return
    shell_path = runner.which(shell)
    if shell_path is None:
        return
    current_shell = runner.run(
        ["sh", "-c", "getent passwd $(whoami) | cut -d: -f7"], check=False
    ).stdout.strip()
    if current_shell == shell_path:
        return
    # chsh may prompt for the user's password.
    runner.run(["chsh", "-s", shell_path], interactive=True)


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


def _to_wsl_path(runner: Runner, distro: str, windows_path: Path) -> str:
    """Convert a Windows path to a WSL path using wslpath."""
    if runner.dry_run:
        drive = windows_path.drive.lower().rstrip(":")
        rest = str(windows_path)[len(windows_path.drive) :].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    result = runner.run(
        ["wsl", "-d", distro, "--", "wslpath", "-u", str(windows_path).replace("\\", "/")],
        check=True,
    )
    return result.stdout.strip()


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
        wsl_source = _to_wsl_path(runner, distro, source)
        runner.run(["wsl", "-d", distro, "--", "cp", wsl_source, destination])
    if CHEAT_SHEET_PATH.exists():
        cheat_destination = f"{wsl_home}/terminal-cheat-sheet.html"
        runner.run(["wsl", "-d", distro, "--", "mkdir", "-p", cheat_destination.rsplit("/", 1)[0]])
        wsl_cheat_source = _to_wsl_path(runner, distro, CHEAT_SHEET_PATH)
        runner.run(["wsl", "-d", distro, "--", "cp", wsl_cheat_source, cheat_destination])


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
            runner.reporter.warn(
                "VS Code settings.json is not strict JSON; skipping terminal profile update "
                "to avoid overwriting existing settings."
            )
            return

    if platform.os == OperatingSystem.WINDOWS:
        distro = _wsl_distro(platform)
        profiles = settings.get("terminal.integrated.profiles.windows", {})
        if not isinstance(profiles, dict):
            profiles = {}

        # Remove synthetic profile from older setup versions.
        profiles.pop("WSL (Default)", None)

        # Remove stale Ubuntu profile when the active distro is a different Ubuntu variant.
        if distro.lower() != "ubuntu":
            profiles.pop("Ubuntu (WSL)", None)

        profile_name = f"{distro} (WSL)"
        profiles[profile_name] = {
            "path": "C:\\Windows\\System32\\wsl.exe",
            "args": ["-d", distro],
            "icon": "terminal-ubuntu",
        }

        settings["terminal.integrated.defaultProfile.windows"] = profile_name
        settings["terminal.integrated.profiles.windows"] = profiles
    elif platform.os == OperatingSystem.LINUX:
        settings["terminal.integrated.defaultProfile.linux"] = "zsh"
    elif platform.os == OperatingSystem.MACOS:
        settings["terminal.integrated.defaultProfile.osx"] = "zsh"

    runner.ensure_dir(settings_path.parent)
    runner.write_text(settings_path, json.dumps(settings, indent=2) + "\n")


def ensure_vscode_extension(runner: Runner, extension_id: str) -> None:
    """Install a VS Code extension if code is available."""
    code_path = runner.which("code")
    if code_path is None:
        return
    if code_path.lower().endswith((".cmd", ".bat")):
        runner.run(["cmd", "/c", code_path, "--install-extension", extension_id])
        return
    runner.run([code_path, "--install-extension", extension_id])


def install_vscode_wsl_extension(runner: Runner, platform: PlatformInfo) -> None:
    """Install the VS Code Remote - WSL extension on Windows."""
    if platform.os != OperatingSystem.WINDOWS:
        return
    ensure_vscode_extension(runner, "ms-vscode-remote.remote-wsl")
