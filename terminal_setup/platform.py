from __future__ import annotations

import os
import platform
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


class OperatingSystem(Enum):
    WINDOWS = auto()
    LINUX = auto()
    MACOS = auto()
    UNKNOWN = auto()


class PackageManager(Enum):
    WINGET = auto()
    APT = auto()
    HOMEBREW = auto()
    PACMAN = auto()
    DNF = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class PlatformInfo:
    os: OperatingSystem
    package_manager: PackageManager
    is_wsl_available: bool
    is_wsl_default_debian_family: bool
    wsl_distribution: str | None
    shell: str
    home: Path
    wezterm_config_dir: Path | None
    vscode_settings_path: Path | None
    wsl_os_id: str | None = None

    @property
    def user_programs_dir(self) -> Path:
        return self.home / "AppData" / "Local" / "Programs"


def detect_os() -> OperatingSystem:
    system = platform.system()
    if system == "Windows":
        return OperatingSystem.WINDOWS
    if system == "Linux":
        return OperatingSystem.LINUX
    if system == "Darwin":
        return OperatingSystem.MACOS
    return OperatingSystem.UNKNOWN


def is_running_in_wsl() -> bool:
    if detect_os() != OperatingSystem.LINUX:
        return False
    try:
        osrelease = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8")
    except OSError:
        return False
    return "microsoft" in osrelease.lower() or "wsl" in osrelease.lower()


def detect_package_manager(os: OperatingSystem) -> PackageManager:
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

    return ["wsl", "-d", distro, "--exec", *command]


def _wsl_command(args: list[str]) -> subprocess.CompletedProcess[str]:

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
    if detect_os() != OperatingSystem.WINDOWS:
        return False
    if not shutil.which("wsl"):
        return False
    result = _wsl_command(["--status"])
    return result.returncode == 0


def get_wsl_default_distribution() -> str | None:
    if not is_wsl_available():
        return None
    result = _wsl_command(["--list", "--verbose"])
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "*" in line:
            return line.replace("*", "").split()[0]
    return None


DEBIAN_FAMILY = frozenset({"debian", "ubuntu"})


def os_release_ids(text: str) -> tuple[str, ...]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip().strip("\"'").lower()
    own = values.get("ID", "")
    return (own, *values.get("ID_LIKE", "").split()) if own else ()


def is_debian_family(ids: tuple[str, ...]) -> bool:
    return any(name in DEBIAN_FAMILY for name in ids)


def read_os_release(distro: str | None) -> str:
    if distro is None:
        try:
            return Path("/etc/os-release").read_text(encoding="utf-8")
        except OSError:
            return ""
    try:
        result = subprocess.run(  # nosec B603
            wsl_exec_command(distro, ["cat", "/etc/os-release"]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return ""
    return result.stdout if result.returncode == 0 else ""


def detect_shell() -> str:
    if detect_os() == OperatingSystem.WINDOWS:
        return "powershell" if shutil.which("powershell") else "cmd"
    shell = shutil.which("zsh") or shutil.which("bash")
    return shell or "/bin/sh"


def get_home_directory() -> Path:
    return Path.home()


def get_wezterm_config_dir() -> Path | None:
    os = detect_os()  # noqa: F841
    home = get_home_directory()
    if detect_os() == OperatingSystem.WINDOWS:
        config_home = Path.home() / ".config"
        return config_home / "wezterm"
    if detect_os() == OperatingSystem.MACOS:
        return home / ".config" / "wezterm"
    return home / ".config" / "wezterm"


def get_vscode_settings_path() -> Path | None:

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
    os = detect_os()
    in_wsl = is_running_in_wsl()
    wsl_available = is_wsl_available() or in_wsl
    default_distro = get_wsl_default_distribution() if wsl_available else None
    if default_distro is None and in_wsl:
        default_distro = _detect_wsl_distro_from_command() or _detect_wsl_distro_from_proc()
    if in_wsl:
        ids = os_release_ids(read_os_release(None))
    elif default_distro is not None:
        ids = os_release_ids(read_os_release(default_distro))
    else:
        ids = ()
    return PlatformInfo(
        os=os,
        package_manager=detect_package_manager(os),
        is_wsl_available=wsl_available,
        is_wsl_default_debian_family=is_debian_family(ids),
        wsl_distribution=default_distro,
        shell=detect_shell(),  # nosec B604
        home=get_home_directory(),
        wezterm_config_dir=get_wezterm_config_dir(),
        vscode_settings_path=get_vscode_settings_path(),
        wsl_os_id=ids[0] if ids else None,
    )


def _detect_wsl_distro_from_proc() -> str | None:
    try:
        osrelease = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    parts = osrelease.split("-")
    if len(parts) >= 2 and parts[-1].lower().startswith("wsl"):
        return parts[-2]
    return None


def _detect_wsl_distro_from_command() -> str | None:
    distro = os.environ.get("WSL_DISTRO_NAME")
    if distro:
        return distro
    return None
