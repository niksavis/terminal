"""Platform detection helpers for the terminal setup."""

from __future__ import annotations

import os
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


def is_running_in_wsl() -> bool:
    """Return True when the current Linux process is inside a WSL environment."""
    if detect_os() != OperatingSystem.LINUX:
        return False
    try:
        osrelease = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8")
    except OSError:
        return False
    return "microsoft" in osrelease.lower() or "wsl" in osrelease.lower()


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


def wsl_exec_command(distro: str, command: list[str]) -> list[str]:
    """Wrap a command so it runs inside a WSL distro without shell re-parsing.

    ``wsl -- <command>`` passes the command line through the guest's default
    shell, which expands ``$variables`` and ``$(...)`` before the target
    command runs and corrupts ``sh -c`` scripts. ``--exec`` hands the
    arguments to the command verbatim, so shell builtins (``command``, ``.``)
    must be invoked via an explicit ``sh -c``.
    """
    return ["wsl", "-d", distro, "--exec", *command]


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
    """Return the VS Code user settings.json path, if discoverable.

    Falls back to the OS-appropriate user-settings location on a fresh
    machine: ``~/.vscode/settings.json`` is never read by VS Code as user
    settings, so writing there would silently no-op.
    """
    home = get_home_directory()
    os = detect_os()
    if os == OperatingSystem.WINDOWS:
        default = home / "AppData" / "Roaming" / "Code" / "User" / "settings.json"
    elif os == OperatingSystem.MACOS:
        default = home / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    else:
        default = home / ".config" / "Code" / "User" / "settings.json"
    candidates = [
        default,
        home / "AppData" / "Roaming" / "Code" / "User" / "settings.json",
        home / "Library" / "Application Support" / "Code" / "User" / "settings.json",
        home / ".config" / "Code" / "User" / "settings.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return default


def detect_platform() -> PlatformInfo:
    """Build a complete platform snapshot."""
    os = detect_os()
    in_wsl = is_running_in_wsl()
    wsl_available = is_wsl_available() or in_wsl
    default_distro = get_wsl_default_distribution() if wsl_available else None
    if default_distro is None and in_wsl:
        default_distro = _detect_wsl_distro_from_command() or _detect_wsl_distro_from_proc()
    return PlatformInfo(
        os=os,
        package_manager=detect_package_manager(os),
        is_wsl_available=wsl_available,
        is_wsl_default_ubuntu=is_wsl_default_ubuntu()
        if not in_wsl
        else default_distro is not None and "ubuntu" in default_distro.lower(),
        wsl_distribution=default_distro,
        shell=detect_shell(),  # nosec B604
        home=get_home_directory(),
        wezterm_config_dir=get_wezterm_config_dir(),
        vscode_settings_path=get_vscode_settings_path(),
    )


def _detect_wsl_distro_from_proc() -> str | None:
    """Return the WSL distribution name from /proc/sys/kernel/osrelease, if present."""
    try:
        osrelease = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    # Common values look like "5.15.146.1-microsoft-standard-WSL2".
    parts = osrelease.split("-")
    if len(parts) >= 2 and parts[-1].lower().startswith("wsl"):
        return parts[-2]
    return None


def _detect_wsl_distro_from_command() -> str | None:
    """Return the current WSL distribution name from the WSLENV variable."""
    distro = os.environ.get("WSL_DISTRO_NAME")
    if distro:
        return distro
    return None
