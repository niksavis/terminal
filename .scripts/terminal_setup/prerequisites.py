"""Prerequisite checking and installation for the terminal setup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .platform import OperatingSystem, PackageManager, PlatformInfo
from .runner import Runner


@dataclass(frozen=True)
class PrerequisiteStatus:
    """Status of a single prerequisite."""

    name: str
    present: bool
    install_command: list[str] | None = None
    message: str = ""


def check_command(runner: Runner, name: str, command: str) -> PrerequisiteStatus:
    """Check whether a command is available on PATH."""
    path = runner.which(command)
    if path:
        return PrerequisiteStatus(name=name, present=True, message=f"found at {path}")
    return PrerequisiteStatus(name=name, present=False, message=f"{command} not found on PATH")


def _wsl_distro(platform: PlatformInfo) -> str:
    """Return the WSL distribution to use, falling back to Ubuntu."""
    return platform.wsl_distribution or "Ubuntu"


def check_wsl_command(
    runner: Runner, platform: PlatformInfo, name: str, command: str
) -> PrerequisiteStatus:
    """Check whether a command is available inside the WSL Ubuntu guest."""
    distro = _wsl_distro(platform)
    result = runner.run(["wsl", "-d", distro, "--", "command", "-v", command], check=False)
    if result.returncode == 0 and result.stdout.strip():
        return PrerequisiteStatus(name=name, present=True, message=result.stdout.strip())
    return PrerequisiteStatus(
        name=name,
        present=False,
        message=f"{command} not found in WSL {distro}",
    )


def check_wsl(platform: PlatformInfo, _runner: Runner) -> PrerequisiteStatus:
    """Check WSL availability and default distribution."""
    if platform.os != OperatingSystem.WINDOWS:
        return PrerequisiteStatus(
            name="wsl",
            present=True,
            message="WSL is not required on non-Windows platforms",
        )
    if not platform.is_wsl_available:
        return PrerequisiteStatus(
            name="wsl",
            present=False,
            message="WSL is not installed or not responsive; enable it via 'wsl --install'",
        )
    if not platform.is_wsl_default_ubuntu:
        return PrerequisiteStatus(
            name="wsl-ubuntu",
            present=False,
            message="WSL default distribution is not Ubuntu; run 'wsl --install -d Ubuntu'",
        )
    return PrerequisiteStatus(
        name="wsl-ubuntu",
        present=True,
        message="WSL is available and defaults to Ubuntu",
    )


def check_package_manager(platform: PlatformInfo) -> PrerequisiteStatus:
    """Check whether a supported package manager is available."""
    if platform.package_manager == PackageManager.UNKNOWN:
        return PrerequisiteStatus(
            name="package-manager",
            present=False,
            message="No supported package manager found (winget, apt, brew, pacman, dnf)",
        )
    return PrerequisiteStatus(
        name="package-manager",
        present=True,
        message=f"found {platform.package_manager.name.lower()}",
    )


def check_all(platform: PlatformInfo, runner: Runner) -> list[PrerequisiteStatus]:
    """Return the status of all prerequisites."""
    statuses = [
        check_package_manager(platform),
        check_wsl(platform, runner),
    ]
    for name, command in [("git", "git"), ("curl", "curl"), ("wget", "wget")]:
        if platform.os == OperatingSystem.WINDOWS:
            statuses.append(check_wsl_command(runner, platform, name, command))
        else:
            statuses.append(check_command(runner, name, command))
    return statuses


def install_package(
    runner: Runner,
    package_manager: PackageManager,
    package: str,
    *,
    wsl_distro: str | None = None,
) -> None:
    """Install a package using the detected package manager."""
    command: list[str]
    if package_manager == PackageManager.WINGET:
        command = [
            "winget",
            "install",
            "--id",
            package,
            "--accept-source-agreements",
            "--accept-package-agreements",
        ]
    elif package_manager == PackageManager.APT:
        command = ["sudo", "apt-get", "install", "-y", package]
    elif package_manager == PackageManager.HOMEBREW:
        command = ["brew", "install", package]
    elif package_manager == PackageManager.PACMAN:
        command = ["sudo", "pacman", "-S", "--noconfirm", package]
    elif package_manager == PackageManager.DNF:
        command = ["sudo", "dnf", "install", "-y", package]
    else:
        raise RuntimeError(f"Unsupported package manager for installing {package}")

    if wsl_distro:
        command = ["wsl", "-d", wsl_distro, "--", *command]

    runner.run(command)


def update_packages(
    runner: Runner,
    package_manager: PackageManager,
    *,
    wsl_distro: str | None = None,
) -> None:
    """Update package lists/indexes."""
    command: list[str]
    if package_manager == PackageManager.APT:
        command = ["sudo", "apt-get", "update"]
    elif package_manager == PackageManager.HOMEBREW:
        command = ["brew", "update"]
    elif package_manager == PackageManager.PACMAN:
        command = ["sudo", "pacman", "-Sy"]
    elif package_manager == PackageManager.DNF:
        command = ["sudo", "dnf", "check-update"]
    else:
        return

    if wsl_distro:
        command = ["wsl", "-d", wsl_distro, "--", *command]

    runner.run(command, check=False)


def install_wsl_ubuntu(runner: Runner) -> None:
    """Install Ubuntu as the default WSL distribution."""
    runner.run(["wsl", "--install", "-d", "Ubuntu"])


def ensure_wsl_tools(runner: Runner, platform: PlatformInfo) -> None:
    """Install core tools inside the WSL Ubuntu guest."""
    distro = _wsl_distro(platform)
    update_packages(runner, PackageManager.APT, wsl_distro=distro)
    for package in ["zsh", "tmux", "git", "curl", "wget"]:
        install_package(runner, PackageManager.APT, package, wsl_distro=distro)


def ensure_wsl_cli_extras(runner: Runner, platform: PlatformInfo) -> None:
    """Install extra CLI tools inside the WSL Ubuntu guest (josean-dev style)."""
    distro = _wsl_distro(platform)
    extras = ["fzf", "fd-find", "bat", "eza", "zoxide", "ripgrep"]
    for package in extras:
        install_package(runner, PackageManager.APT, package, wsl_distro=distro)
    # Create common binary aliases for Debian/Ubuntu package names.
    fd_alias = "command -v fdfind >/dev/null && ln -sf $(command -v fdfind) ~/.local/bin/fd || true"
    bat_alias = (
        "command -v batcat >/dev/null && ln -sf $(command -v batcat) ~/.local/bin/bat || true"
    )
    runner.run(["wsl", "-d", distro, "--", "sh", "-c", fd_alias])
    runner.run(["wsl", "-d", distro, "--", "sh", "-c", bat_alias])
    runner.ensure_dir(platform.home / ".local" / "bin")


def ensure_shell_tools(runner: Runner, platform: PlatformInfo) -> None:
    """Install core shell tools on the host."""
    if platform.os == OperatingSystem.WINDOWS:
        return
    packages = {
        PackageManager.APT: ["zsh", "tmux", "git", "curl", "wget"],
        PackageManager.HOMEBREW: ["zsh", "tmux", "git", "curl", "wget"],
        PackageManager.PACMAN: ["zsh", "tmux", "git", "curl", "wget"],
        PackageManager.DNF: ["zsh", "tmux", "git", "curl", "wget"],
    }
    for package in packages.get(platform.package_manager, []):
        install_package(runner, platform.package_manager, package)


def ensure_host_cli_extras(runner: Runner, platform: PlatformInfo) -> None:
    """Install extra CLI tools on the host (josean-dev style)."""
    if platform.os == OperatingSystem.WINDOWS:
        return
    extras = {
        PackageManager.APT: ["fzf", "fd-find", "bat", "eza", "zoxide", "ripgrep"],
        PackageManager.HOMEBREW: ["fzf", "fd", "bat", "eza", "zoxide", "ripgrep"],
        PackageManager.PACMAN: ["fzf", "fd", "bat", "eza", "zoxide", "ripgrep"],
        PackageManager.DNF: ["fzf", "fd-find", "bat", "eza", "zoxide", "ripgrep"],
    }
    for package in extras.get(platform.package_manager, []):
        install_package(runner, platform.package_manager, package)


def ensure_starship(runner: Runner, platform: PlatformInfo) -> None:
    """Install the starship prompt if possible."""
    if runner.which("starship"):
        return
    if platform.os == OperatingSystem.WINDOWS:
        if runner.which("winget"):
            runner.run(
                [
                    "winget",
                    "install",
                    "--id",
                    "Starship.Starship",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                ]
            )
        return
    if platform.os == OperatingSystem.LINUX:
        script_url = "https://starship.rs/install.sh"
        runner.run(["sh", "-c", f"curl -fsSL {script_url} | sh -s -- -y"])
        return
    if platform.os == OperatingSystem.MACOS and platform.package_manager == PackageManager.HOMEBREW:
        install_package(runner, PackageManager.HOMEBREW, "starship")


def ensure_wezterm(runner: Runner, platform: PlatformInfo) -> None:
    """Install WezTerm using the platform package manager."""
    if runner.which("wezterm"):
        return
    if platform.os == OperatingSystem.WINDOWS and platform.package_manager == PackageManager.WINGET:
        runner.run(
            [
                "winget",
                "install",
                "--id",
                "wez.wezterm",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ]
        )
        return
    if platform.os == OperatingSystem.MACOS and platform.package_manager == PackageManager.HOMEBREW:
        install_package(runner, PackageManager.HOMEBREW, "--cask", "wezterm")
        return
    if platform.os == OperatingSystem.LINUX:
        if platform.package_manager == PackageManager.APT:
            _ensure_wezterm_apt(runner)
        elif platform.package_manager == PackageManager.PACMAN:
            install_package(runner, PackageManager.PACMAN, "wezterm")
        elif platform.package_manager == PackageManager.DNF:
            install_package(runner, PackageManager.DNF, "wezterm")


def _ensure_wezterm_apt(runner: Runner) -> None:
    """Add the WezTerm apt repository and install."""
    keyring_dir = Path("/usr/share/keyrings")
    keyring_path = keyring_dir / "wezterm-fury.gpg"
    if not runner.dry_run and not keyring_path.exists():
        runner.run(["sudo", "mkdir", "-p", str(keyring_dir)])
        runner.run(
            [
                "bash",
                "-c",
                f"curl -fsSL https://fury.wez.dev/key.gpg | sudo gpg --dearmor -o {keyring_path}",
            ]
        )
    sources_line = f"deb [signed-by={keyring_path}] https://fury.wez.dev/apt/ * *"
    sources_path = Path("/etc/apt/sources.list.d/wezterm.list")
    if not runner.dry_run and not sources_path.exists():
        runner.run(["bash", "-c", f"echo '{sources_line}' | sudo tee {sources_path}"])
    update_packages(runner, PackageManager.APT)
    install_package(runner, PackageManager.APT, "wezterm")
