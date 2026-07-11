"""Platform detection helpers for the terminal setup."""

from __future__ import annotations

import platform
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


class OperatingSystem(Enum):
    """Supported operating systems."""

    WINDOWS = auto()
    LINUX = auto()
    MACOS = auto()
    UNKNOWN = auto()


class PackageManager(Enum):
    """Detected package managers."""

    WINGET = auto()
    APT = auto()
    HOMEBREW = auto()
    PACMAN = auto()
    DNF = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class PlatformInfo:
    """Snapshot of the current platform."""

    os: OperatingSystem
    package_manager: PackageManager
    is_wsl_available: bool
    is_wsl_default_ubuntu: bool
    wsl_distribution: str | None
    shell: str
    home: Path
    wezterm_config_dir: Path | None
    vscode_settings_path: Path | None
    user_install: bool = False

    @property
    def user_programs_dir(self) -> Path:
        """Return the per-user programs directory used for non-admin installs."""
        return self.home / "AppData" / "Local" / "Programs"


def detect_os() -> OperatingSystem:
    """Return the current operating system enum."""
    system = platform.system()
    if system == "Windows":
        return OperatingSystem.WINDOWS
    if system == "Linux":
        return OperatingSystem.LINUX
    if system == "Darwin":
        return OperatingSystem.MACOS
    return OperatingSystem.UNKNOWN


def detect_package_manager(os: OperatingSystem) -> PackageManager:
    """Return the preferred package manager for the platform."""
    if os == OperatingSystem.WINDOWS and shutil.which("winget"):
        return PackageManager.WINGET
    if os == OperatingSystem.MACOS and shutil.which("brew"):
        return PackageManager.HOMEBREW
    if os == OperatingSystem.LINUX:
        if shutil.which("apt"):
            return PackageManager.APT
        if shutil.which("pacman"):
            return PackageManager.PACMAN
        if shutil.which("dnf"):
            return PackageManager.DNF
    return PackageManager.UNKNOWN


def _wsl_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a WSL command and return the result.

    WSL list output is UTF-16LE encoded, so we decode it explicitly.
    """
    result = subprocess.run(  # nosec
        ["wsl", *args],
        capture_output=True,
        check=False,
    )
    return subprocess.CompletedProcess(
        args=result.args,
        returncode=result.returncode,
        stdout=result.stdout.decode("utf-16le", errors="replace").replace("\x00", ""),
        stderr=result.stderr.decode("utf-8", errors="replace"),
    )


def is_wsl_available() -> bool:
    """Check whether WSL is installed and responsive."""
    if detect_os() != OperatingSystem.WINDOWS:
        return False
    if not shutil.which("wsl"):
        return False
    result = _wsl_command(["--status"])
    return result.returncode == 0


def get_wsl_default_distribution() -> str | None:
    """Return the default WSL distribution name, or None."""
    if not is_wsl_available():
        return None
    result = _wsl_command(["--list", "--verbose"])
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "*" in line:
            return line.replace("*", "").split()[0]
    return None


def is_wsl_default_ubuntu() -> bool:
    """Check whether the default WSL distribution is Ubuntu."""
    default = get_wsl_default_distribution()
    return default is not None and "ubuntu" in default.lower()


def detect_shell() -> str:
    """Return the user's current login shell."""
    if detect_os() == OperatingSystem.WINDOWS:
        return "powershell" if shutil.which("powershell") else "cmd"
    shell = shutil.which("zsh") or shutil.which("bash")
    return shell or "/bin/sh"


def get_home_directory() -> Path:
    """Return the user's home directory."""
    return Path.home()


def get_wezterm_config_dir() -> Path | None:
    """Return the WezTerm configuration directory for the platform."""
    os = detect_os()  # noqa: F841
    home = get_home_directory()
    if detect_os() == OperatingSystem.WINDOWS:
        config_home = Path.home() / ".config"
        return config_home / "wezterm"
    if detect_os() == OperatingSystem.MACOS:
        return home / ".config" / "wezterm"
    return home / ".config" / "wezterm"


def get_vscode_settings_path() -> Path | None:
    """Return the VS Code settings.json path, if discoverable."""
    home = get_home_directory()
    candidates = [
        home / ".vscode" / "settings.json",
        home / "AppData" / "Roaming" / "Code" / "User" / "settings.json",
        home / "Library" / "Application Support" / "Code" / "User" / "settings.json",
        home / ".config" / "Code" / "User" / "settings.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None


def detect_platform(user_install: bool = False) -> PlatformInfo:
    """Build a complete platform snapshot."""
    os = detect_os()
    wsl_available = is_wsl_available()
    default_distro = get_wsl_default_distribution() if wsl_available else None
    return PlatformInfo(
        os=os,
        package_manager=detect_package_manager(os),
        is_wsl_available=wsl_available,
        is_wsl_default_ubuntu=is_wsl_default_ubuntu(),
        wsl_distribution=default_distro,
        shell=detect_shell(),  # nosec B604
        home=get_home_directory(),
        wezterm_config_dir=get_wezterm_config_dir(),
        vscode_settings_path=get_vscode_settings_path(),
        user_install=user_install,
    )
