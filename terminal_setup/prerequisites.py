"""Prerequisite checking and installation for the terminal setup."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path

from .platform import (
    OperatingSystem,
    PackageManager,
    PlatformInfo,
    is_running_in_wsl,
    wsl_exec_command,
)
from .runner import Runner


@dataclass(frozen=True)
class PrerequisiteStatus:
    """Status of a single prerequisite."""

    name: str
    present: bool
    install_command: list[str] | None = None
    message: str = ""


# Node.js major version to install in WSL/Linux/macOS, matching the Windows
# runtime. Track the current active major so both sides stay aligned.
TARGET_NODE_MAJOR = "24"


@dataclass(frozen=True)
class SystemVersionPolicy:
    """Policy for handling pre-existing system-wide tool installations."""

    uninstall: bool = False
    keep: bool = False


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
    if is_running_in_wsl():
        result = runner.run(
            ["sh", "-c", f"command -v {command}"],
            check=False,
            dry_run_safe=True,
        )
    else:
        result = runner.run(
            wsl_exec_command(distro, ["sh", "-c", f"command -v {command}"]),
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
    if is_running_in_wsl():
        return PrerequisiteStatus(
            name="wsl",
            present=True,
            message="Running inside WSL",
        )
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


def _is_wsl_target(platform: PlatformInfo) -> bool:
    """Return True when the WSL toolset should be installed into a distro."""
    return is_running_in_wsl() or platform.os == OperatingSystem.WINDOWS


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
        if _is_wsl_target(platform):
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
    if package_manager == PackageManager.WINGET:
        if _is_winget_package_installed(runner, package):
            runner.reporter.info(f"{package} is already installed; skipping")
            return
    elif package_manager == PackageManager.APT and not _apt_package_available(
        runner, package, wsl_distro=wsl_distro
    ):
        if _install_apt_fallback(runner, package, wsl_distro=wsl_distro):
            return
        raise RuntimeError(f"Package '{package}' is not available via apt")

    if package_manager in {
        PackageManager.APT,
        PackageManager.HOMEBREW,
        PackageManager.PACMAN,
        PackageManager.DNF,
    } and not _should_install_package_update(
        runner,
        package_manager,
        package,
        wsl_distro=wsl_distro,
    ):
        return

    command = _package_install_command(package_manager, package)

    if wsl_distro and not is_running_in_wsl():
        command = wsl_exec_command(wsl_distro, command)

    # apt/pacman/dnf run under sudo and may prompt for a password.
    interactive = package_manager in {
        PackageManager.APT,
        PackageManager.PACMAN,
        PackageManager.DNF,
    }
    runner.run(command, interactive=interactive)


def _package_install_command(package_manager: PackageManager, package: str) -> list[str]:
    """Return the install command for a package manager and package."""
    if package_manager == PackageManager.WINGET:
        return [
            "winget",
            "install",
            "--id",
            package,
            "--accept-source-agreements",
            "--accept-package-agreements",
        ]
    if package_manager == PackageManager.APT:
        return ["sudo", "apt-get", "install", "-y", package]
    if package_manager == PackageManager.HOMEBREW:
        return ["brew", "install", package]
    if package_manager == PackageManager.PACMAN:
        return ["sudo", "pacman", "-S", "--noconfirm", package]
    if package_manager == PackageManager.DNF:
        return ["sudo", "dnf", "install", "-y", package]
    raise RuntimeError(f"Unsupported package manager for installing {package}")


def _apt_package_available(runner: Runner, package: str, *, wsl_distro: str | None = None) -> bool:
    """Return whether a package exists in apt metadata."""
    command = ["apt-cache", "show", package]
    if wsl_distro and not is_running_in_wsl():
        command = wsl_exec_command(wsl_distro, command)
    result = runner.run(command, check=False, dry_run_safe=True)
    return result.returncode == 0


def _parse_field(output: str, field: str) -> str | None:
    """Return a value from `<Field>: <value>` lines in command output."""
    prefix = f"{field}:"
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped.split(":", 1)[1].strip()
            return value or None
    return None


def _package_versions(
    runner: Runner,
    package_manager: PackageManager,
    package: str,
    *,
    wsl_distro: str | None = None,
) -> tuple[str | None, str | None]:
    """Return `(installed, latest)` versions for a package manager package."""
    if package_manager == PackageManager.APT:
        return _apt_package_versions(runner, package, wsl_distro=wsl_distro)

    if package_manager == PackageManager.HOMEBREW:
        return _brew_package_versions(runner, package)

    if package_manager == PackageManager.PACMAN:
        return _pacman_package_versions(runner, package)

    if package_manager == PackageManager.DNF:
        return _dnf_package_versions(runner, package)

    return None, None


def _apt_package_versions(
    runner: Runner,
    package: str,
    *,
    wsl_distro: str | None = None,
) -> tuple[str | None, str | None]:
    """Return `(installed, latest)` versions for apt packages."""
    command = ["apt-cache", "policy", package]
    if wsl_distro and not is_running_in_wsl():
        command = wsl_exec_command(wsl_distro, command)
    result = runner.run(command, check=False, dry_run_safe=True)
    if result.returncode != 0:
        return None, None
    installed = _parse_field(result.stdout, "Installed")
    latest = _parse_field(result.stdout, "Candidate")
    if installed == "(none)":
        installed = None
    if latest == "(none)":
        latest = None
    return installed, latest


def _brew_package_versions(runner: Runner, package: str) -> tuple[str | None, str | None]:
    """Return `(installed, latest)` versions for Homebrew packages."""
    installed_command = ["brew", "list", "--versions", package]
    installed_result = runner.run(installed_command, check=False, dry_run_safe=True)
    installed = None
    if installed_result.returncode == 0 and installed_result.stdout.strip():
        parts = installed_result.stdout.strip().split()
        installed = parts[1] if len(parts) > 1 else None

    info_command = ["brew", "info", "--json=v2", package]
    info_result = runner.run(info_command, check=False, dry_run_safe=True)
    latest = None
    if info_result.returncode == 0 and info_result.stdout.strip():
        try:
            payload = json.loads(info_result.stdout)
            formulae = payload.get("formulae", [])
            if formulae:
                latest = formulae[0].get("versions", {}).get("stable")
            casks = payload.get("casks", [])
            if latest is None and casks:
                cask_version = casks[0].get("version")
                latest = cask_version if cask_version != "latest" else None
        except json.JSONDecodeError:
            latest = None
    return installed, latest


def _pacman_package_versions(runner: Runner, package: str) -> tuple[str | None, str | None]:
    """Return `(installed, latest)` versions for pacman packages."""
    installed_command = ["pacman", "-Qi", package]
    latest_command = ["pacman", "-Si", package]
    installed_result = runner.run(installed_command, check=False, dry_run_safe=True)
    latest_result = runner.run(latest_command, check=False, dry_run_safe=True)
    installed = _parse_field(installed_result.stdout, "Version")
    latest = _parse_field(latest_result.stdout, "Version")
    return installed, latest


def _dnf_package_versions(runner: Runner, package: str) -> tuple[str | None, str | None]:
    """Return `(installed, latest)` versions for dnf packages."""
    installed_command = ["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}\\n", package]
    installed_result = runner.run(installed_command, check=False, dry_run_safe=True)
    installed = installed_result.stdout.strip() if installed_result.returncode == 0 else None
    if installed == "":
        installed = None

    latest_command = ["dnf", "--showduplicates", "list", package]
    latest_result = runner.run(latest_command, check=False, dry_run_safe=True)
    latest = None
    if latest_result.returncode in {0, 100}:
        versions: list[str] = []
        for line in latest_result.stdout.splitlines():
            columns = line.split()
            if len(columns) < 2:
                continue
            name = columns[0]
            if name == package or name.startswith(f"{package}."):
                versions.append(columns[1])
        if versions:
            latest = versions[-1]
    return installed, latest


def _should_install_package_update(
    runner: Runner,
    package_manager: PackageManager,
    package: str,
    *,
    wsl_distro: str | None = None,
) -> bool:
    """Return whether a package install/update should run."""
    installed, latest = _package_versions(
        runner,
        package_manager,
        package,
        wsl_distro=wsl_distro,
    )
    if installed is None:
        return True

    if latest is None or latest == installed:
        runner.reporter.info(f"{package} is up to date ({installed}); skipping")
        return False

    prompt = f"Update {package} from {installed} to {latest}?"
    if runner.dry_run:
        runner.reporter.info(f"Would ask: {prompt} (answer 'no' by default in dry-run mode)")
        return False
    if runner.confirm(prompt):
        return True
    runner.reporter.info(f"Skipping {package} update")
    return False


def _command_available(runner: Runner, command: str, *, wsl_distro: str | None = None) -> bool:
    """Return whether a command is available on host or in WSL."""
    if wsl_distro is None or is_running_in_wsl():
        if runner.which(command) is not None:
            return True
        return _is_user_local_command_available(runner, command)

    script = (
        f"if test -x ~/.local/bin/{command}; then exit 0; fi; command -v {command} >/dev/null 2>&1"
    )
    result = runner.run(
        wsl_exec_command(wsl_distro, ["sh", "-c", script]),
        check=False,
        dry_run_safe=True,
    )
    return result.returncode == 0


def _is_user_local_command_available(
    runner: Runner,
    command: str,
    *,
    wsl_distro: str | None = None,
) -> bool:
    """Return whether a command exists as an executable in ~/.local/bin."""
    if wsl_distro and not is_running_in_wsl():
        result = runner.run(
            wsl_exec_command(wsl_distro, ["sh", "-c", f"test -x ~/.local/bin/{command}"]),
            check=False,
            dry_run_safe=True,
        )
        return result.returncode == 0

    local_bin = Path.home() / ".local" / "bin" / command
    if runner.dry_run:
        return local_bin.exists()
    return local_bin.exists() and os.access(local_bin, os.X_OK)


def _run_shell_command(runner: Runner, script: str, *, wsl_distro: str | None = None) -> None:
    """Run a shell command on host or in WSL."""
    command = ["sh", "-c", script]
    if wsl_distro and not is_running_in_wsl():
        command = wsl_exec_command(wsl_distro, command)
    runner.run(command, interactive=True)


def _run_shell_read(
    runner: Runner,
    script: str,
    *,
    wsl_distro: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a read-only shell command on host or in WSL and capture output."""
    command = ["sh", "-c", script]
    if wsl_distro and not is_running_in_wsl():
        command = wsl_exec_command(wsl_distro, command)
    return runner.run(command, check=False, dry_run_safe=True)


def _ensure_rustup_cargo(runner: Runner, *, wsl_distro: str | None = None) -> None:
    """Ensure a modern cargo toolchain is available for Rust fallback installs."""
    if (wsl_distro is None or is_running_in_wsl()) and (
        Path.home() / ".cargo" / "bin" / "cargo"
    ).exists():
        return
    if wsl_distro is not None and not is_running_in_wsl():
        result = runner.run(
            wsl_exec_command(wsl_distro, ["sh", "-c", "test -x ~/.cargo/bin/cargo"]),
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
    # ast-grep is checked via its full binary name: probing `sg` false-positives
    # on util-linux's /usr/bin/sg.
    rust_fallback = {
        "ast-grep": ("ast-grep", "ast-grep"),
        "typos": ("typos-cli", "typos"),
        "just": ("just", "just"),
    }
    if package in rust_fallback:
        crate, command = rust_fallback[package]
        if not _command_available(runner, command, wsl_distro=wsl_distro):
            _ensure_rustup_cargo(runner, wsl_distro=wsl_distro)
            _run_shell_command(
                runner,
                (
                    'if [ -f "$HOME/.cargo/env" ]; then . "$HOME/.cargo/env"; fi; '
                    f"cargo install --locked --force --root ~/.local {crate}"
                ),
                wsl_distro=wsl_distro,
            )
        return True

    if package == "xh":
        if not _command_available(runner, "xh", wsl_distro=wsl_distro):
            _run_shell_command(
                runner,
                "curl -sfL https://raw.githubusercontent.com/ducaale/xh/master/install.sh | sh",
                wsl_distro=wsl_distro,
            )
        return True

    if package == "uv":
        if not _command_available(runner, "uv", wsl_distro=wsl_distro):
            _run_shell_command(
                runner,
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
                wsl_distro=wsl_distro,
            )
        return True

    if package == "lazygit":
        _install_lazygit_release(runner, wsl_distro=wsl_distro, no_sudo=False)
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

    if wsl_distro and not is_running_in_wsl():
        command = wsl_exec_command(wsl_distro, command)

    # apt/pacman may prompt for a password via sudo.
    interactive = package_manager in {PackageManager.APT, PackageManager.PACMAN}
    runner.run(command, check=False, interactive=interactive)


def install_wsl_ubuntu(runner: Runner) -> None:
    """Install Ubuntu as the default WSL distribution."""
    runner.run(["wsl", "--install", "-d", "Ubuntu"])


def _wsl_apt_install_script(packages: list[str]) -> str:
    """Return a shell script that updates apt and installs packages in one session."""
    package_list = " ".join(packages)
    # Safety: remove only known legacy WezTerm source files/entries before apt update.
    # Using rm -f keeps this cleanup idempotent and avoids failures when files are absent.
    return (
        "set -e; "
        "sudo sh -c '"
        "set -e; "
        "export DEBIAN_FRONTEND=noninteractive; "
        "rm -f /etc/apt/sources.list.d/wezterm.list "
        "/etc/apt/sources.list.d/wezterm.sources "
        "/etc/apt/sources.list.d/wezterm-fury.list "
        "/etc/apt/sources.list.d/wezterm-fury.sources; "
        "for file in /etc/apt/sources.list.d/*; do "
        '[ -f "$file" ] || continue; '
        'if grep -Eq "fury\\\\.wez\\\\.dev|apt\\\\.fury\\\\.io/wez" "$file"; then '
        'rm -f "$file"; '
        "fi; "
        "done; "
        "if [ -f /etc/apt/sources.list ] && "
        'grep -Eq "fury\\\\.wez\\\\.dev|apt\\\\.fury\\\\.io/wez" /etc/apt/sources.list; then '
        'sed -i "/fury\\\\.wez\\\\.dev/d;/apt\\\\.fury\\\\.io\\\\/wez/d" /etc/apt/sources.list; '
        "fi; "
        "apt-get update; "
        f"apt-get install -y {package_list}"
        "'"
    )


def _run_in_wsl_or_host(
    runner: Runner,
    command: list[str],
    *,
    distro: str | None,
    interactive: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command directly on the host or wrap it for WSL when called from Windows."""
    if distro and not is_running_in_wsl():
        command = wsl_exec_command(distro, command)
    return runner.run(command, interactive=interactive)


def _wsl_apt_install_command(runner: Runner, packages: list[str], distro: str) -> None:
    """Run the apt install script either directly in WSL or via wsl.exe from Windows."""
    script = _wsl_apt_install_script(packages)
    _run_in_wsl_or_host(
        runner,
        ["sh", "-c", script],
        distro=distro,
        interactive=True,
    )


def _split_wsl_packages_by_install_path(
    runner: Runner,
    packages: list[str],
    *,
    distro: str,
) -> tuple[list[str], list[str]]:
    """Split WSL packages into apt-installable and fallback groups."""
    apt_packages: list[str] = []
    fallback_packages: list[str] = []
    for package in packages:
        if package == "lazygit":
            fallback_packages.append(package)
            continue
        if _apt_package_available(runner, package, wsl_distro=distro):
            apt_packages.append(package)
        else:
            fallback_packages.append(package)
    return apt_packages, fallback_packages


def _find_system_command_path(
    runner: Runner,
    command: str,
    *,
    wsl_distro: str | None = None,
) -> str | None:
    """Return the path to a system-wide command, or None if it is absent."""
    lookup_command = ["sh", "-c", f"command -v {command}"]
    if wsl_distro and not is_running_in_wsl():
        lookup_command = wsl_exec_command(wsl_distro, lookup_command)

    result = runner.run(lookup_command, check=False, dry_run_safe=True)
    if result.returncode != 0:
        return None
    path = result.stdout.strip()
    if path.startswith(("/usr/", "/bin/")) and not path.startswith(str(Path.home())):
        return path
    return None


def _find_owning_package(
    runner: Runner,
    path: str,
    package_manager: PackageManager,
    *,
    wsl_distro: str | None = None,
) -> str | None:
    """Return the package that owns a given file path, if detectable."""
    command: list[str] | None = None
    if package_manager == PackageManager.APT:
        command = ["dpkg", "-S", path]
    elif package_manager == PackageManager.PACMAN:
        command = ["pacman", "-Qo", path]
    elif package_manager == PackageManager.DNF:
        command = ["rpm", "-qf", path]
    if command is None:
        return None

    if wsl_distro and not is_running_in_wsl():
        command = wsl_exec_command(wsl_distro, command)
    result = runner.run(command, check=False, dry_run_safe=True)
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    if package_manager == PackageManager.APT and ":" in output:
        return output.split(":", 1)[0].strip()
    if package_manager == PackageManager.PACMAN and "owned by" in output:
        parts = output.split("owned by")
        if len(parts) >= 2:
            return parts[1].strip().split()[0]
    if package_manager == PackageManager.DNF:
        return output.split("-")[0].strip() if output else None
    return None


def _uninstall_package(
    runner: Runner,
    package: str,
    package_manager: PackageManager,
    *,
    wsl_distro: str | None = None,
) -> None:
    """Remove a package using the detected package manager."""
    command: list[str]
    if package_manager == PackageManager.APT:
        command = ["sudo", "apt-get", "remove", "-y", package]
    elif package_manager == PackageManager.PACMAN:
        command = ["sudo", "pacman", "-R", "--noconfirm", package]
    elif package_manager == PackageManager.DNF:
        command = ["sudo", "dnf", "remove", "-y", package]
    else:
        raise RuntimeError(f"Unsupported package manager for removing {package}")

    if wsl_distro and not is_running_in_wsl():
        command = wsl_exec_command(wsl_distro, command)
    runner.run(command, interactive=True)


def _warn_or_uninstall_system_version(
    runner: Runner,
    command: str,
    package_manager: PackageManager,
    *,
    wsl_distro: str | None = None,
    policy: SystemVersionPolicy | None = None,
) -> None:
    """Warn about a system-wide version and optionally offer to remove it.

    When ``policy.uninstall`` is True the system package is removed without
    prompting. When ``policy.keep`` is True only a warning is printed.
    Otherwise the user is asked interactively.
    """
    resolved_policy = policy or SystemVersionPolicy()
    path = _find_system_command_path(runner, command, wsl_distro=wsl_distro)
    if path is None:
        return

    package = _find_owning_package(runner, path, package_manager, wsl_distro=wsl_distro)
    if package is None:
        runner.reporter.warn(
            f"{command} is already installed system-wide at {path}. "
            "A user-local copy will be installed in ~/.local/bin. "
            "You can remove the system version later if the local one works."
        )
        return

    if resolved_policy.keep:
        runner.reporter.warn(
            f"{command} is already installed system-wide at {path} (package: {package}). "
            "Keeping the system version because --keep-system-versions was requested."
        )
        return

    if resolved_policy.uninstall:
        runner.reporter.info(
            f"Removing system package {package} ({command} at {path}) because "
            "--uninstall-system-versions was requested."
        )
        _uninstall_package(runner, package, package_manager, wsl_distro=wsl_distro)
        return

    prompt = (
        f"{command} is already installed system-wide at {path} (package: {package}). "
        "Remove the system version so the user-local copy in ~/.local/bin takes precedence?"
    )
    if runner.dry_run:
        runner.reporter.info(f"Would ask: {prompt} (answer 'no' by default in dry-run mode)")
        return
    if runner.confirm(prompt):
        _uninstall_package(runner, package, package_manager, wsl_distro=wsl_distro)
    else:
        runner.reporter.info(
            f"Keeping system package {package}; the user-local copy will still be installed."
        )


def _install_cargo_tool(
    runner: Runner,
    crate: str,
    binary: str,
    *,
    wsl_distro: str | None = None,
) -> None:
    """Install a Rust crate into ~/.local using cargo."""
    del binary
    _ensure_rustup_cargo(runner, wsl_distro=wsl_distro)
    _run_shell_command(
        runner,
        (
            'if [ -f "$HOME/.cargo/env" ]; then . "$HOME/.cargo/env"; fi; '
            f"cargo install --locked --force --root ~/.local {crate}"
        ),
        wsl_distro=wsl_distro,
    )


def _install_fzf_binary(runner: Runner, *, wsl_distro: str | None = None) -> None:
    """Download the fzf binary to ~/.local/bin."""
    script = (
        "set -e; "
        "arch=$(uname -m); "
        "case $arch in x86_64) arch=amd64;; aarch64) arch=arm64;; esac; "
        "tmp=$(mktemp -d); "
        "release=$(curl -s https://api.github.com/repos/junegunn/fzf/releases/latest | "
        'sed -n \'s/.*"tag_name": *"\\([^"]*\\)".*/\\1/p\'); '
        "version=${release#v}; "
        'url="https://github.com/junegunn/fzf/releases/download/${release}/'
        'fzf-${version}-linux_${arch}.tar.gz"; '
        "curl -fsSL -o $tmp/fzf.tar.gz $url; "
        "tar -xzf $tmp/fzf.tar.gz -C $tmp; "
        "mkdir -p ~/.local/bin; "
        "mv $tmp/fzf ~/.local/bin/fzf; "
        "rm -rf $tmp"
    )
    _run_shell_command(runner, script, wsl_distro=wsl_distro)


def _install_jq_binary(runner: Runner, *, wsl_distro: str | None = None) -> None:
    """Download the jq binary to ~/.local/bin."""
    script = (
        "set -e; "
        "arch=$(uname -m); "
        "case $arch in x86_64) arch=amd64;; aarch64) arch=arm64;; esac; "
        "mkdir -p ~/.local/bin; "
        "curl -fsSL -o ~/.local/bin/jq "
        "https://github.com/jqlang/jq/releases/latest/download/jq-linux-${arch}; "
        "chmod +x ~/.local/bin/jq"
    )
    _run_shell_command(runner, script, wsl_distro=wsl_distro)


def _install_yq_binary(runner: Runner, *, wsl_distro: str | None = None) -> None:
    """Download the yq binary to ~/.local/bin."""
    script = (
        "set -e; "
        "arch=$(uname -m); "
        "case $arch in x86_64) arch=amd64;; aarch64) arch=arm64;; esac; "
        "mkdir -p ~/.local/bin; "
        "curl -fsSL -o ~/.local/bin/yq "
        "https://github.com/mikefarah/yq/releases/latest/download/yq_linux_${arch}; "
        "chmod +x ~/.local/bin/yq"
    )
    _run_shell_command(runner, script, wsl_distro=wsl_distro)


def _install_shellcheck_binary(runner: Runner, *, wsl_distro: str | None = None) -> None:
    """Download the shellcheck binary to ~/.local/bin."""
    script = (
        "set -e; "
        "arch=$(uname -m); "
        "case $arch in x86_64) arch=x86_64;; aarch64) arch=aarch64;; esac; "
        "tmp=$(mktemp -d); "
        "release=$(curl -s https://api.github.com/repos/koalaman/shellcheck/releases/latest | "
        'sed -n \'s/.*"tag_name": *"\\([^"]*\\)".*/\\1/p\'); '
        'url="https://github.com/koalaman/shellcheck/releases/download/${release}/'
        'shellcheck-${release}.linux.${arch}.tar.xz"; '
        "curl -fsSL -o $tmp/sc.tar.xz $url; "
        "tar -xf $tmp/sc.tar.xz -C $tmp; "
        "mkdir -p ~/.local/bin; "
        "mv $tmp/shellcheck-${release}/shellcheck ~/.local/bin/shellcheck; "
        "rm -rf $tmp"
    )
    _run_shell_command(runner, script, wsl_distro=wsl_distro)


def _install_node_binary(runner: Runner, *, wsl_distro: str | None = None) -> None:
    """Install the latest Node.js ``TARGET_NODE_MAJOR`` release into ~/.local.

    Downloads the official prebuilt tarball and merges its bin/lib/include/share
    into ~/.local (npm and npx are relative symlinks into lib), so Node installs
    without sudo and matches the Windows major version.
    """
    script = (
        "set -e; "
        "arch=$(uname -m); "
        "case $arch in x86_64) arch=x64;; aarch64|arm64) arch=arm64;; esac; "
        "os=$(uname -s | tr 'A-Z' 'a-z'); "
        "case $os in darwin) os=darwin;; *) os=linux;; esac; "
        "ver=$(curl -fsSL https://nodejs.org/dist/index.json "
        f'| grep -o \'"version":"v{TARGET_NODE_MAJOR}[^"]*"\' | head -n 1 | cut -d\'"\' -f4); '
        '[ -n "$ver" ] || { echo "Unable to resolve latest Node.js version" >&2; exit 1; }; '
        "tmp=$(mktemp -d); "
        'pkg="node-${ver}-${os}-${arch}"; '
        'curl -fsSL -o "$tmp/node.tar.xz" "https://nodejs.org/dist/${ver}/${pkg}.tar.xz"; '
        'tar -xJf "$tmp/node.tar.xz" -C "$tmp"; '
        "mkdir -p ~/.local; "
        'cp -R "$tmp/${pkg}/." ~/.local/; '
        'rm -rf "$tmp"'
    )
    _run_shell_command(runner, script, wsl_distro=wsl_distro)


def ensure_node(runner: Runner, platform: PlatformInfo) -> None:
    """Install Node.js user-locally where it is missing.

    Node is installed without sudo into ~/.local, matching the major version
    used on Windows. On Windows the WSL guest is targeted; Windows-native Node
    is managed outside this setup.
    """
    if platform.os == OperatingSystem.WINDOWS:
        distro = _wsl_distro(platform)
        if not _command_available(runner, "node", wsl_distro=distro):
            _install_node_binary(runner, wsl_distro=distro)
        return
    if platform.os not in {OperatingSystem.LINUX, OperatingSystem.MACOS}:
        return
    if _command_available(runner, "node"):
        return
    _install_node_binary(runner)


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    """Convert a version string into an integer tuple for comparison."""
    core = version.split("-", 1)[0].split("+", 1)[0]
    values: list[int] = []
    for chunk in core.split("."):
        if chunk.isdigit():
            values.append(int(chunk))
            continue
        digits = "".join(char for char in chunk if char.isdigit())
        if digits:
            values.append(int(digits))
        else:
            break
    return tuple(values)


def _is_version_at_least(current: str, latest: str) -> bool:
    """Return True when current version is greater than or equal to latest."""
    current_tuple = _parse_version_tuple(current)
    latest_tuple = _parse_version_tuple(latest)
    if not current_tuple or not latest_tuple:
        return False
    width = max(len(current_tuple), len(latest_tuple))
    padded_current = current_tuple + (0,) * (width - len(current_tuple))
    padded_latest = latest_tuple + (0,) * (width - len(latest_tuple))
    return padded_current >= padded_latest


def _latest_lazygit_version(runner: Runner, *, wsl_distro: str | None = None) -> str | None:
    """Return the latest tagged lazygit version from upstream releases."""
    script = (
        "curl -fsSL https://api.github.com/repos/jesseduffield/lazygit/releases/latest "
        '| sed -n \'s/.*"tag_name": *"v\\([^"]*\\)".*/\\1/p\' | head -n 1'
    )
    result = _run_shell_read(runner, script, wsl_distro=wsl_distro)
    if result.returncode != 0:
        return None
    version = result.stdout.strip()
    return version or None


def _installed_lazygit_version(runner: Runner, *, wsl_distro: str | None = None) -> str | None:
    """Return the installed lazygit version, or None when unavailable."""
    # Prefer ~/.local/bin: non-login shells miss it on PATH, and reporting the
    # stale system copy would re-prompt for an update on every run.
    script = (
        'PATH="$HOME/.local/bin:$PATH"; '
        "if ! command -v lazygit >/dev/null 2>&1; then exit 0; fi; "
        "lazygit --version 2>/dev/null "
        "| grep -Eo 'version=[0-9][0-9.]*' | head -n 1 | cut -d= -f2"
    )
    result = _run_shell_read(runner, script, wsl_distro=wsl_distro)
    if result.returncode != 0:
        return None
    version = result.stdout.strip()
    return version or None


def _install_lazygit_release(
    runner: Runner,
    *,
    wsl_distro: str | None = None,
    no_sudo: bool,
) -> None:
    """Install the latest lazygit binary from upstream releases."""
    latest_version = _latest_lazygit_version(runner, wsl_distro=wsl_distro)
    if latest_version is None:
        raise RuntimeError("Unable to resolve latest lazygit version")

    installed_version = _installed_lazygit_version(runner, wsl_distro=wsl_distro)
    if installed_version and _is_version_at_least(installed_version, latest_version):
        message = (
            "lazygit is already up to date "
            f"(installed: {installed_version}, latest: {latest_version})"
        )
        runner.reporter.info(message)
        return

    if installed_version:
        prompt = f"Update lazygit from {installed_version} to {latest_version}?"
        if runner.dry_run:
            runner.reporter.info(f"Would ask: {prompt} (answer 'no' by default in dry-run mode)")
            return
        if not runner.confirm(prompt):
            runner.reporter.info("Skipping lazygit update")
            return

    install_command = 'mkdir -p ~/.local/bin; install -m 0755 "$tmp/lazygit" ~/.local/bin/lazygit'
    if not no_sudo:
        install_command = 'sudo install -m 0755 "$tmp/lazygit" /usr/local/bin/lazygit'

    script = (
        "set -e; "
        'os="$(uname -s)"; '
        'if [ "$os" = "Linux" ]; then os="Linux"; '
        'elif [ "$os" = "Darwin" ]; then os="Darwin"; '
        'else echo "Unsupported OS for lazygit: $os" >&2; exit 1; fi; '
        'arch="$(uname -m)"; '
        'if [ "$arch" = "x86_64" ] || [ "$arch" = "amd64" ]; then arch="x86_64"; '
        'elif [ "$arch" = "aarch64" ] || [ "$arch" = "arm64" ]; then arch="arm64"; '
        'else echo "Unsupported arch for lazygit: $arch" >&2; exit 1; fi; '
        "tmp=$(mktemp -d); "
        f'version="{latest_version}"; '
        'curl -fLo "$tmp/lazygit.tar.gz" '
        '"https://github.com/jesseduffield/lazygit/releases/download/'
        'v${version}/lazygit_${version}_${os}_${arch}.tar.gz"; '
        'tar -xf "$tmp/lazygit.tar.gz" -C "$tmp" lazygit; '
        f"{install_command}; "
        'rm -rf "$tmp"'
    )
    _run_shell_command(runner, script, wsl_distro=wsl_distro)


def _command_for_package(package: str) -> str:
    """Return the command name for a package (Debian package names differ from binaries)."""
    # ast-grep maps to its full binary name: probing `sg` false-positives on
    # util-linux's /usr/bin/sg.
    mapping = {
        "fd-find": "fd",
        "bat": "bat",
        "ripgrep": "rg",
        "ast-grep": "ast-grep",
        "git-delta": "delta",
        "typos-cli": "typos",
    }
    return mapping.get(package, package)


def _system_version_policy(
    *,
    uninstall_system_versions: bool = False,
    keep_system_versions: bool = False,
) -> SystemVersionPolicy:
    """Build a policy from the CLI flags."""
    return SystemVersionPolicy(
        uninstall=uninstall_system_versions,
        keep=keep_system_versions,
    )


def _install_user_local_tool(
    runner: Runner,
    package: str,
    platform: PlatformInfo,
    *,
    policy: SystemVersionPolicy | None = None,
) -> bool:
    """Install a tool into user-writable locations without sudo.

    Returns True when a user-local install path is known for the package.
    """
    cargo_tools: dict[str, tuple[str, str]] = {
        "fd-find": ("fd-find", "fd"),
        "bat": ("bat", "bat"),
        "ripgrep": ("ripgrep", "rg"),
        "xh": ("xh", "xh"),
        "ast-grep": ("ast-grep", "ast-grep"),
        "sd": ("sd", "sd"),
        "just": ("just", "just"),
        "git-delta": ("git-delta", "delta"),
        "typos": ("typos-cli", "typos"),
    }
    distro = _wsl_distro(platform)
    if package in cargo_tools:
        crate, binary = cargo_tools[package]
        _warn_or_uninstall_system_version(
            runner,
            binary,
            platform.package_manager,
            wsl_distro=distro,
            policy=policy,
        )
        _install_cargo_tool(runner, crate, binary, wsl_distro=distro)
        return True

    static_binaries = {
        "fzf": _install_fzf_binary,
        "jq": _install_jq_binary,
        "yq": _install_yq_binary,
        "shellcheck": _install_shellcheck_binary,
    }
    if package in static_binaries:
        _warn_or_uninstall_system_version(
            runner,
            package,
            platform.package_manager,
            wsl_distro=distro,
            policy=policy,
        )
        static_binaries[package](runner, wsl_distro=distro)
        return True

    if package == "uv":
        _warn_or_uninstall_system_version(
            runner,
            "uv",
            platform.package_manager,
            wsl_distro=distro,
            policy=policy,
        )
        _run_shell_command(
            runner,
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            wsl_distro=distro,
        )
        return True

    if package == "lazygit":
        _warn_or_uninstall_system_version(
            runner,
            "lazygit",
            platform.package_manager,
            wsl_distro=distro,
            policy=policy,
        )
        _install_lazygit_release(runner, wsl_distro=distro, no_sudo=True)
        return True

    return False


def _require_interactive_stdin_for_sudo(runner: Runner) -> None:
    """Fail fast when sudo would prompt for a password without a terminal.

    sudo reads the password from the controlling terminal, so in headless
    contexts (agents, CI, hidden consoles) the setup would hang forever on an
    invisible prompt instead of failing.
    """
    if runner.dry_run or sys.stdin.isatty():
        return
    raise RuntimeError(
        "This step may require a sudo password but stdin is not an interactive "
        "terminal. Re-run from an interactive shell, or use --user-install / "
        "--no-sudo to install into user-writable locations without sudo."
    )


def ensure_wsl_tools(
    runner: Runner,
    platform: PlatformInfo,
    *,
    no_sudo: bool = False,
    uninstall_system_versions: bool = False,
    keep_system_versions: bool = False,
) -> None:
    """Install core tools inside the WSL Ubuntu guest."""
    distro = _wsl_distro(platform)
    policy = _system_version_policy(
        uninstall_system_versions=uninstall_system_versions,
        keep_system_versions=keep_system_versions,
    )
    packages = [
        "zsh",
        "tmux",
        "git",
        "lazygit",
        "git-lfs",
        "direnv",
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
        "xh",
        "ast-grep",
        "sd",
        "just",
        "git-delta",
        "typos",
        "uv",
    ]

    if no_sudo:
        runner.reporter.info("--no-sudo requested: installing tools into user-writable locations.")
        base_packages = {"zsh", "tmux", "git", "curl", "wget", "tree"}
        for package in packages:
            command = _command_for_package(package)
            if package in base_packages:
                if not _command_available(runner, command, wsl_distro=distro):
                    runner.reporter.warn(
                        f"{package} is not installed and requires sudo to install via apt; "
                        "skipping."
                    )
                continue
            if package != "lazygit" and _command_available(runner, command, wsl_distro=distro):
                continue
            if not _install_user_local_tool(runner, package, platform, policy=policy):
                runner.reporter.warn(f"No user-local install path known for {package}; skipping.")
        return

    _require_interactive_stdin_for_sudo(runner)
    apt_packages, fallback_packages = _split_wsl_packages_by_install_path(
        runner,
        packages,
        distro=distro,
    )

    if apt_packages:
        _wsl_apt_install_command(runner, apt_packages, distro)

    for package in fallback_packages:
        if not _install_apt_fallback(runner, package, wsl_distro=distro):
            raise RuntimeError(f"Package '{package}' is not available via apt")


def ensure_wsl_cli_extras(runner: Runner, platform: PlatformInfo) -> None:
    """Install post-package CLI extras inside the WSL Ubuntu guest."""
    distro = _wsl_distro(platform)
    _run_in_wsl_or_host(runner, ["sh", "-c", "mkdir -p ~/.local/bin"], distro=distro)
    # Create common binary aliases for Debian/Ubuntu package names. Skip when a
    # user-local binary already exists so cargo-installed copies are not clobbered.
    fd_alias = (
        "[ -e ~/.local/bin/fd ] || { command -v fdfind >/dev/null "
        "&& ln -sf $(command -v fdfind) ~/.local/bin/fd; } || true"
    )
    bat_alias = (
        "[ -e ~/.local/bin/bat ] || { command -v batcat >/dev/null "
        "&& ln -sf $(command -v batcat) ~/.local/bin/bat; } || true"
    )
    _run_in_wsl_or_host(runner, ["sh", "-c", fd_alias], distro=distro)
    _run_in_wsl_or_host(runner, ["sh", "-c", bat_alias], distro=distro)


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
            "git-lfs",
            "direnv",
            "fzf",
            "fd-find",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "xh",
            "ast-grep",
            "sd",
            "just",
            "git-delta",
            "typos",
            "uv",
        ],
        PackageManager.HOMEBREW: [
            "git-lfs",
            "direnv",
            "fzf",
            "fd",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "xh",
            "ast-grep",
            "sd",
            "just",
            "git-delta",
            "typos-cli",
            "uv",
        ],
        PackageManager.PACMAN: [
            "git-lfs",
            "direnv",
            "fzf",
            "fd",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "xh",
            "ast-grep",
            "sd",
            "just",
            "git-delta",
            "typos",
            "uv",
        ],
        PackageManager.DNF: [
            "git-lfs",
            "direnv",
            "fzf",
            "fd-find",
            "bat",
            "ripgrep",
            "jq",
            "yq",
            "shellcheck",
            "tree",
            "xh",
            "ast-grep",
            "sd",
            "just",
            "git-delta",
            "typos",
            "uv",
        ],
    }
    for package in extras.get(platform.package_manager, []):
        install_package(runner, platform.package_manager, package)
    _install_lazygit_release(runner, no_sudo=False)


def _ensure_starship_user_install(runner: Runner, platform: PlatformInfo) -> None:
    """Install starship into the user's programs directory without admin rights."""
    install_dir = platform.user_programs_dir / "starship"
    runner.ensure_dir(install_dir)
    install_dir_str = str(install_dir).replace("\\", "/")
    api_url = "https://api.github.com/repos/starship/starship/releases/latest"
    base_url = "https://github.com/starship/starship/releases/download"
    script = (
        f"$ErrorActionPreference = 'Stop'; "
        f"$release = (Invoke-RestMethod -Uri '{api_url}' -UseBasicParsing).tag_name; "
        f"$url = '{base_url}/' + $release + '/starship-x86_64-pc-windows-msvc.zip'; "
        f"$zip = Join-Path $env:TEMP 'starship.zip'; "
        f"Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing; "
        f"Expand-Archive -Path $zip -DestinationPath '{install_dir_str}' -Force; "
        f"Remove-Item $zip"
    )
    runner.run(["powershell", "-Command", script], interactive=True)
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
        install_script = (
            f"mkdir -p ~/.local/bin && curl -fsSL {script_url} | sh -s -- -y -b ~/.local/bin"
        )
        runner.run(["sh", "-c", install_script])
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
    # The release zip nests everything under a WezTerm-windows-<tag>/ folder;
    # flatten it so wezterm.exe lands directly in the install directory.
    script = (
        f"$ErrorActionPreference = 'Stop'; "
        f"$release = (Invoke-RestMethod -Uri '{api_url}' -UseBasicParsing).tag_name; "
        f"$url = '{base_url}/' + $release + '/WezTerm-windows-' + $release + '.zip'; "
        f"$zip = Join-Path $env:TEMP 'wezterm.zip'; "
        f"Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing; "
        f"$extract = Join-Path $env:TEMP 'wezterm-extract'; "
        f"if (Test-Path $extract) {{ Remove-Item $extract -Recurse -Force }}; "
        f"Expand-Archive -Path $zip -DestinationPath $extract -Force; "
        f"$inner = Get-ChildItem -Path $extract -Directory | Select-Object -First 1; "
        f"$source = if ($inner -and -not (Get-ChildItem -Path $extract -File)) "
        f"{{ $inner.FullName }} else {{ $extract }}; "
        f"Copy-Item -Path (Join-Path $source '*') -Destination '{install_dir_str}' "
        f"-Recurse -Force; "
        f"Remove-Item $zip; "
        f"Remove-Item $extract -Recurse -Force"
    )
    runner.run(["powershell", "-Command", script], interactive=True)
    _add_to_user_path(runner, install_dir)


def _ensure_wezterm_windows(runner: Runner, platform: PlatformInfo, *, user_install: bool) -> None:
    """Install WezTerm on Windows via existing installs, winget, or a user download."""
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
    if platform.package_manager != PackageManager.WINGET:
        return
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


def ensure_wezterm(
    runner: Runner, platform: PlatformInfo, *, user_install: bool = False, no_sudo: bool = False
) -> None:
    """Install WezTerm using the platform package manager."""
    if runner.which("wezterm"):
        return
    if platform.os == OperatingSystem.WINDOWS:
        _ensure_wezterm_windows(runner, platform, user_install=user_install)
        return
    if platform.os == OperatingSystem.MACOS and platform.package_manager == PackageManager.HOMEBREW:
        runner.run(["brew", "install", "--cask", "wezterm"])
        return
    if platform.os != OperatingSystem.LINUX:
        return
    if platform.package_manager == PackageManager.APT:
        if no_sudo:
            runner.reporter.info(
                "--no-sudo requested: skipping WezTerm apt repo and using AppImage fallback."
            )
            _ensure_wezterm_appimage(runner)
        else:
            _ensure_wezterm_apt(runner)
    elif platform.package_manager == PackageManager.PACMAN:
        install_package(runner, PackageManager.PACMAN, "wezterm")
    elif platform.package_manager == PackageManager.DNF:
        install_package(runner, PackageManager.DNF, "wezterm")


def _ensure_wezterm_apt(runner: Runner) -> None:
    """Add the WezTerm apt repository and install.

    Matches the official instructions at https://wezterm.org/install/linux.html.
    Warn and continue if the WezTerm repository is unreachable or the package
    is unavailable, so that a transient network issue does not block the rest
    of the setup.
    """
    keyring_dir = Path("/usr/share/keyrings")
    keyring_path = keyring_dir / "wezterm-fury.gpg"
    _require_interactive_stdin_for_sudo(runner)
    if not runner.dry_run and not keyring_path.exists():
        runner.run(["sudo", "mkdir", "-p", str(keyring_dir)], interactive=True)
        gpg_script = (
            "curl -fsSL https://apt.fury.io/wez/gpg.key | "
            f"sudo gpg --yes --dearmor -o {keyring_path}"
        )
        runner.run(["bash", "-c", gpg_script], interactive=True)
        runner.run(["sudo", "chmod", "644", str(keyring_path)], interactive=True)
    sources_line = f"deb [signed-by={keyring_path}] https://apt.fury.io/wez/ * *"
    sources_path = Path("/etc/apt/sources.list.d/wezterm.list")
    if not runner.dry_run and not sources_path.exists():
        runner.run(
            ["bash", "-c", f"echo '{sources_line}' | sudo tee {sources_path}"],
            interactive=True,
        )
    update_packages(runner, PackageManager.APT)
    if _apt_package_available(runner, "wezterm"):
        install_package(runner, PackageManager.APT, "wezterm")
        return
    runner.reporter.warn(
        "WezTerm apt package is not available (repository may be unreachable); "
        "falling back to AppImage."
    )
    _ensure_wezterm_appimage(runner)


def _ensure_wezterm_appimage(runner: Runner) -> None:
    """Download the WezTerm AppImage to ~/.local/bin as a fallback."""
    appimage_url = (
        "https://github.com/wezterm/wezterm/releases/download/nightly/"
        "WezTerm-nightly-Ubuntu24.04.AppImage"
    )
    install_dir = Path.home() / ".local" / "bin"
    target = install_dir / "wezterm"
    script = f"mkdir -p {install_dir}; curl -fsSL -o {target} {appimage_url}; chmod +x {target}"
    runner.run(["sh", "-c", script], interactive=True)
