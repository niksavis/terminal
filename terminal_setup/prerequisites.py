"""Prerequisite checking and installation for the terminal setup."""

from __future__ import annotations

import os
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
    # Prerequisite checks are read-only and should reflect reality even in dry-run.
    result = runner.run(
        ["wsl", "-d", distro, "--", "command", "-v", command],
        check=False,
        dry_run_safe=True,
    )
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
        if not _apt_package_available(runner, package, wsl_distro=wsl_distro):
            if _install_apt_fallback(runner, package, wsl_distro=wsl_distro):
                return
            raise RuntimeError(f"Package '{package}' is not available via apt")
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

    # apt/pacman/dnf run under sudo and may prompt for a password.
    interactive = package_manager in {
        PackageManager.APT,
        PackageManager.PACMAN,
        PackageManager.DNF,
    }
    runner.run(command, interactive=interactive)


def _apt_package_available(runner: Runner, package: str, *, wsl_distro: str | None = None) -> bool:
    """Return whether a package exists in apt metadata."""
    command = ["apt-cache", "show", package]
    if wsl_distro:
        command = ["wsl", "-d", wsl_distro, "--", *command]
    result = runner.run(command, check=False, dry_run_safe=True)
    return result.returncode == 0


def _command_available(runner: Runner, command: str, *, wsl_distro: str | None = None) -> bool:
    """Return whether a command is available on host or in WSL."""
    if wsl_distro is None:
        return runner.which(command) is not None
    result = runner.run(
        ["wsl", "-d", wsl_distro, "--", "sh", "-c", f"command -v {command}"],
        check=False,
        dry_run_safe=True,
    )
    return result.returncode == 0


def _run_shell_command(runner: Runner, script: str, *, wsl_distro: str | None = None) -> None:
    """Run a shell command on host or in WSL."""
    command = ["sh", "-c", script]
    if wsl_distro:
        command = ["wsl", "-d", wsl_distro, "--", *command]
    runner.run(command, interactive=True)


def _ensure_rustup_cargo(runner: Runner, *, wsl_distro: str | None = None) -> None:
    """Ensure a modern cargo toolchain is available for Rust fallback installs."""
    if wsl_distro is None and (Path.home() / ".cargo" / "bin" / "cargo").exists():
        return
    if wsl_distro is not None:
        result = runner.run(
            ["wsl", "-d", wsl_distro, "--", "sh", "-c", "test -x ~/.cargo/bin/cargo"],
            check=False,
            dry_run_safe=True,
        )
        if result.returncode == 0:
            return
    _run_shell_command(
        runner,
        "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
        wsl_distro=wsl_distro,
    )


def _install_apt_fallback(runner: Runner, package: str, *, wsl_distro: str | None = None) -> bool:
    """Install unsupported apt packages via a supported fallback path."""
    rust_fallback = {
        "ast-grep": ("ast-grep", "sg"),
        "typos": ("typos-cli", "typos"),
    }
    if package in rust_fallback:
        crate, command = rust_fallback[package]
        if _command_available(runner, command, wsl_distro=wsl_distro):
            return True
        _ensure_rustup_cargo(runner, wsl_distro=wsl_distro)
        _run_shell_command(
            runner,
            (
                'CARGO_BIN="$HOME/.cargo/bin/cargo"; '
                'if [ ! -x "$CARGO_BIN" ]; then CARGO_BIN="$(command -v cargo)"; fi; '
                f'"$CARGO_BIN" install --locked --root ~/.local {crate}'
            ),
            wsl_distro=wsl_distro,
        )
        return True

    if package == "uv":
        if _command_available(runner, "uv", wsl_distro=wsl_distro):
            return True
        _run_shell_command(
            runner,
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            wsl_distro=wsl_distro,
        )
        return True

    return False


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

    # apt/pacman may prompt for a password via sudo.
    interactive = package_manager in {PackageManager.APT, PackageManager.PACMAN}
    runner.run(command, check=False, interactive=interactive)


def install_wsl_ubuntu(runner: Runner) -> None:
    """Install Ubuntu as the default WSL distribution."""
    runner.run(["wsl", "--install", "-d", "Ubuntu"])


def _wsl_apt_install_script(packages: list[str]) -> str:
    """Return a shell script that updates apt and installs packages in one session."""
    package_list = " ".join(packages)
    return (
        "set -e; "
        "sudo sh -c '"
        "set -e; "
        "export DEBIAN_FRONTEND=noninteractive; "
        "apt-get update; "
        f"apt-get install -y {package_list}"
        "'"
    )


def ensure_wsl_tools(runner: Runner, platform: PlatformInfo) -> None:
    """Install core tools inside the WSL Ubuntu guest."""
    distro = _wsl_distro(platform)
    packages = [
        "zsh",
        "tmux",
        "git",
        "curl",
        "wget",
        "fzf",
        "fd-find",
        "bat",
        "ripgrep",
        "jq",
        "yq",
        "shellcheck",
        "tree",
        "ast-grep",
        "sd",
        "git-delta",
        "typos",
        "uv",
    ]
    script = _wsl_apt_install_script(packages)
    runner.run(["wsl", "-d", distro, "--", "sh", "-c", script], interactive=True)


def ensure_wsl_cli_extras(runner: Runner, platform: PlatformInfo) -> None:
    """Install post-package CLI extras inside the WSL Ubuntu guest."""
    distro = _wsl_distro(platform)
    runner.run(["wsl", "-d", distro, "--", "sh", "-c", "mkdir -p ~/.local/bin"])
    starship_install = (
        "[ -x ~/.local/bin/starship ] "
        "|| (curl -fsSL https://starship.rs/install.sh | sh -s -- -y -b ~/.local/bin)"
    )
    runner.run(["wsl", "-d", distro, "--", "sh", "-c", starship_install], interactive=True)
    # Create common binary aliases for Debian/Ubuntu package names.
    fd_alias = "command -v fdfind >/dev/null && ln -sf $(command -v fdfind) ~/.local/bin/fd || true"
    bat_alias = (
        "command -v batcat >/dev/null && ln -sf $(command -v batcat) ~/.local/bin/bat || true"
    )
    runner.run(["wsl", "-d", distro, "--", "sh", "-c", fd_alias])
    runner.run(["wsl", "-d", distro, "--", "sh", "-c", bat_alias])


def _is_winget_package_installed(runner: Runner, package_id: str) -> bool:
    """Return whether a winget package is already installed."""
    if runner.which("winget") is None:
        return False
    result = runner.run(
        ["winget", "list", "--id", package_id],
        check=False,
        dry_run_safe=True,
    )
    if result.returncode != 0:
        return False
    return package_id.lower() in result.stdout.lower()


def _add_to_process_path(directory: Path) -> None:
    """Add a directory to the current process PATH so checks in this run can find it."""
    directory_str = str(directory)
    current = os.environ.get("PATH", "")
    entries = current.split(";") if current else []
    if directory_str not in entries:
        os.environ["PATH"] = f"{directory_str};{current}" if current else directory_str


def _ensure_windows_command_in_path(
    runner: Runner,
    command_name: str,
    candidate_dirs: list[Path],
) -> bool:
    """Try to locate a Windows executable in known directories and add it to PATH."""
    if runner.which(command_name):
        return True
    executable_name = f"{command_name}.exe"
    for directory in candidate_dirs:
        executable = directory / executable_name
        if not executable.exists():
            continue
        _add_to_user_path(runner, directory)
        _add_to_process_path(directory)
        return runner.which(command_name) is not None
    return False


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
    """Install agent-first CLI tools on the host."""
    if platform.os == OperatingSystem.WINDOWS:
        return
    extras = {
        PackageManager.APT: [
            "fzf",
            "fd-find",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "ast-grep",
            "sd",
            "git-delta",
            "typos",
            "uv",
        ],
        PackageManager.HOMEBREW: [
            "fzf",
            "fd",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "ast-grep",
            "sd",
            "git-delta",
            "typos-cli",
            "uv",
        ],
        PackageManager.PACMAN: [
            "fzf",
            "fd",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "ast-grep",
            "sd",
            "git-delta",
            "typos",
            "uv",
        ],
        PackageManager.DNF: [
            "fzf",
            "fd-find",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "ast-grep",
            "sd",
            "git-delta",
            "typos",
            "uv",
        ],
    }
    for package in extras.get(platform.package_manager, []):
        install_package(runner, platform.package_manager, package)


def _ensure_starship_user_install(runner: Runner, platform: PlatformInfo) -> None:
    """Install starship into the user's programs directory without admin rights."""
    install_dir = platform.user_programs_dir / "starship"
    runner.ensure_dir(install_dir)
    install_dir_str = str(install_dir).replace("\\", "/")
    script_url = "https://starship.rs/install.sh"
    runner.run(
        [
            "powershell",
            "-Command",
            f"& {{ $ErrorActionPreference = 'Stop'; "
            f"Invoke-WebRequest -Uri {script_url} -UseBasicParsing | "
            f"Invoke-Expression; install -y -b '{install_dir_str}' }}",
        ],
        interactive=True,
    )
    _add_to_user_path(runner, install_dir)


def ensure_starship(runner: Runner, platform: PlatformInfo, *, user_install: bool = False) -> None:
    """Install the starship prompt if possible."""
    if runner.which("starship"):
        return
    if platform.os == OperatingSystem.WINDOWS:
        _ensure_windows_command_in_path(
            runner,
            "starship",
            [
                Path("C:/Program Files/starship/bin"),
                platform.user_programs_dir / "starship",
                platform.user_programs_dir / "starship" / "bin",
            ],
        )
        if runner.which("starship"):
            return
        if _is_winget_package_installed(runner, "Starship.Starship"):
            return
        if user_install:
            _ensure_starship_user_install(runner, platform)
            return
        if runner.which("winget"):
            result = runner.run(
                [
                    "winget",
                    "install",
                    "--id",
                    "Starship.Starship",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                    "--scope",
                    "user",
                ],
                check=False,
                interactive=True,
            )
            if result.returncode != 0 and not _is_winget_package_installed(
                runner, "Starship.Starship"
            ):
                raise RuntimeError("Failed to install starship via winget")
            _ensure_windows_command_in_path(
                runner,
                "starship",
                [
                    Path("C:/Program Files/starship/bin"),
                    platform.user_programs_dir / "starship",
                    platform.user_programs_dir / "starship" / "bin",
                ],
            )
        return
    if platform.os == OperatingSystem.LINUX:
        script_url = "https://starship.rs/install.sh"
        runner.run(["sh", "-c", f"curl -fsSL {script_url} | sh -s -- -y"])
        return
    if platform.os == OperatingSystem.MACOS and platform.package_manager == PackageManager.HOMEBREW:
        install_package(runner, PackageManager.HOMEBREW, "starship")


def _add_to_user_path(runner: Runner, directory: Path) -> None:
    """Add a directory to the user's PATH persistently on Windows."""
    if runner.dry_run:
        return
    directory_str = str(directory).replace("\\", "/")
    script = (
        f"$target = [Environment]::GetEnvironmentVariable('PATH', 'User'); "
        f"if ($target -notlike '*{directory_str}*') {{ "
        f"[Environment]::SetEnvironmentVariable("
        f"'PATH', $target + ';{directory_str}', 'User') }}"
    )
    runner.run(["powershell", "-Command", script], interactive=True)
    _add_to_process_path(directory)


def _ensure_wezterm_user_install(runner: Runner, platform: PlatformInfo) -> None:
    """Download and extract WezTerm to the user's programs directory."""
    install_dir = platform.user_programs_dir / "WezTerm"
    runner.ensure_dir(install_dir)
    install_dir_str = str(install_dir).replace("\\", "/")
    api_url = "https://api.github.com/repos/wez/wezterm/releases/latest"
    base_url = "https://github.com/wez/wezterm/releases/download"
    script = (
        f"$ErrorActionPreference = 'Stop'; "
        f"$release = (Invoke-RestMethod -Uri '{api_url}' -UseBasicParsing).tag_name; "
        f"$url = '{base_url}/' + $release + '/WezTerm-windows-' + $release + '.zip'; "
        f"$zip = Join-Path $env:TEMP 'wezterm.zip'; "
        f"Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing; "
        f"Expand-Archive -Path $zip -DestinationPath '{install_dir_str}' -Force; "
        f"Remove-Item $zip"
    )
    runner.run(["powershell", "-Command", script], interactive=True)
    _add_to_user_path(runner, install_dir)


def ensure_wezterm(runner: Runner, platform: PlatformInfo, *, user_install: bool = False) -> None:
    """Install WezTerm using the platform package manager."""
    if runner.which("wezterm"):
        return
    if platform.os == OperatingSystem.WINDOWS:
        _ensure_windows_command_in_path(
            runner,
            "wezterm",
            [
                Path("C:/Program Files/WezTerm"),
                Path("C:/Program Files (x86)/WezTerm"),
                platform.user_programs_dir / "WezTerm",
            ],
        )
        if runner.which("wezterm"):
            return
        if _is_winget_package_installed(runner, "wez.wezterm"):
            return
        if user_install:
            _ensure_wezterm_user_install(runner, platform)
            return
        if platform.package_manager == PackageManager.WINGET:
            result = runner.run(
                [
                    "winget",
                    "install",
                    "--id",
                    "wez.wezterm",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                    "--scope",
                    "user",
                ],
                check=False,
                interactive=True,
            )
            if result.returncode != 0 and not _is_winget_package_installed(runner, "wez.wezterm"):
                raise RuntimeError("Failed to install WezTerm via winget")
            _ensure_windows_command_in_path(
                runner,
                "wezterm",
                [
                    Path("C:/Program Files/WezTerm"),
                    Path("C:/Program Files (x86)/WezTerm"),
                    platform.user_programs_dir / "WezTerm",
                ],
            )
        return
    if platform.os == OperatingSystem.MACOS and platform.package_manager == PackageManager.HOMEBREW:
        runner.run(["brew", "install", "--cask", "wezterm"])
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
        runner.run(["sudo", "mkdir", "-p", str(keyring_dir)], interactive=True)
        runner.run(
            [
                "bash",
                "-c",
                f"curl -fsSL https://fury.wez.dev/key.gpg | sudo gpg --dearmor -o {keyring_path}",
            ],
            interactive=True,
        )
    sources_line = f"deb [signed-by={keyring_path}] https://fury.wez.dev/apt/ * *"
    sources_path = Path("/etc/apt/sources.list.d/wezterm.list")
    if not runner.dry_run and not sources_path.exists():
        runner.run(
            ["bash", "-c", f"echo '{sources_line}' | sudo tee {sources_path}"],
            interactive=True,
        )
    update_packages(runner, PackageManager.APT)
    install_package(runner, PackageManager.APT, "wezterm")
