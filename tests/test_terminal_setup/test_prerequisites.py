"""Tests for prerequisite checking and installation helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast
from unittest import mock

from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo, detect_os
from terminal_setup.prerequisites import (
    PrerequisiteStatus,
    SystemVersionPolicy,
    check_all,
    check_command,
    check_package_manager,
    check_wsl,
    ensure_host_cli_extras,
    ensure_wsl_tools,
)
from terminal_setup.prerequisites import (
    _find_owning_package as find_owning_package,
)
from terminal_setup.prerequisites import (
    _find_system_command_path as find_system_command_path,
)
from terminal_setup.prerequisites import (
    _system_version_policy as system_version_policy,
)
from terminal_setup.prerequisites import (
    _warn_or_uninstall_system_version as warn_or_uninstall_system_version,
)
from terminal_setup.runner import Runner


def make_platform(os: OperatingSystem, package_manager: PackageManager) -> PlatformInfo:
    """Build a PlatformInfo for testing."""
    return PlatformInfo(
        os=os,
        package_manager=package_manager,
        is_wsl_available=False,
        is_wsl_default_ubuntu=False,
        wsl_distribution="Ubuntu" if os == OperatingSystem.WINDOWS else None,
        shell="/bin/zsh",
        home=Path.home(),
        wezterm_config_dir=Path.home() / ".config" / "wezterm",
        vscode_settings_path=None,
    )


class SpyRunner:
    """Lightweight runner that records commands for package-install assertions."""

    def __init__(self) -> None:
        """Initialize the recorded command list."""
        self.commands: list[list[str]] = []

    def run(  # noqa: PLR0913
        self,
        command: list[str],
        *,
        check: bool = True,
        dry_run_safe: bool = False,
        interactive: bool = False,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Record a command and return a successful completed process."""
        del check, dry_run_safe, interactive, cwd, env
        self.commands.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")


class FakeReporter:
    """Reporter that records messages and answers no to confirmations."""

    def __init__(self) -> None:
        """Initialize the message list."""
        self.messages: list[tuple[str, str]] = []

    def info(self, message: str) -> None:
        """Record an informational message."""
        self.messages.append(("info", message))

    def warn(self, message: str) -> None:
        """Record a warning message."""
        self.messages.append(("warn", message))

    def error(self, message: str) -> None:
        """Record an error message."""
        self.messages.append(("error", message))

    def command(self, command: list[str]) -> None:
        """Record a command that would run."""
        self.messages.append(("command", " ".join(command)))

    def confirm(self, message: str) -> bool:
        """Record a confirmation prompt and answer no by default."""
        self.messages.append(("confirm", message))
        return False


class FakeRunner:
    """Runner that returns configured command outputs and records executions."""

    def __init__(self, outputs: dict[tuple[str, ...], tuple[int, str]] | None = None) -> None:
        """Initialize with a mapping from command tuples to (returncode, stdout)."""
        self.outputs = outputs or {}
        self.commands: list[list[str]] = []
        self.dry_run = False
        self.confirm_answer = False
        self.confirm_prompts: list[str] = []
        self.reporter = FakeReporter()

    def run(  # noqa: PLR0913
        self,
        command: list[str],
        *,
        check: bool = True,
        dry_run_safe: bool = False,
        interactive: bool = False,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Return a configured output for known commands and record all commands."""
        del check, dry_run_safe, interactive, cwd, env
        self.commands.append(command)
        key = tuple(command)
        returncode, stdout = self.outputs.get(key, (0, ""))
        return subprocess.CompletedProcess(args=command, returncode=returncode, stdout=stdout)

    def which(self, _command: str) -> str | None:
        """Pretend the command is missing."""
        return None

    def confirm(self, prompt: str) -> bool:
        """Record the prompt and return the configured answer."""
        self.confirm_prompts.append(prompt)
        return self.confirm_answer


def _installed_packages(commands: list[list[str]], manager: PackageManager) -> list[str]:
    """Extract package names from install commands for a specific package manager."""
    packages: list[str] = []
    for command in commands:
        if manager == PackageManager.APT and command[:4] == ["sudo", "apt-get", "install", "-y"]:
            packages.append(command[4])
        if manager == PackageManager.HOMEBREW and command[:2] == ["brew", "install"]:
            packages.append(command[2])
        if manager == PackageManager.PACMAN and command[:4] == [
            "sudo",
            "pacman",
            "-S",
            "--noconfirm",
        ]:
            packages.append(command[4])
        if manager == PackageManager.DNF and command[:4] == ["sudo", "dnf", "install", "-y"]:
            packages.append(command[4])
    return packages


def test_check_command_finds_existing_command() -> None:
    """check_command must report present for a command that exists on PATH."""
    runner = Runner(dry_run=True)
    status = check_command(runner, "python", "python")
    assert status.present is True
    assert "python" in status.message


def test_check_command_missing_command() -> None:
    """check_command must report missing for a non-existent command."""
    runner = Runner(dry_run=True)
    status = check_command(runner, "not-a-real-tool", "not-a-real-tool-xyz")
    assert status.present is False


def test_check_package_manager_unknown() -> None:
    """check_package_manager must report missing when no manager is found."""
    platform = make_platform(OperatingSystem.LINUX, PackageManager.UNKNOWN)
    status = check_package_manager(platform)
    assert status.present is False


def test_check_package_manager_known() -> None:
    """check_package_manager must report present for a known manager."""
    platform = make_platform(OperatingSystem.LINUX, PackageManager.APT)
    status = check_package_manager(platform)
    assert status.present is True


def test_check_wsl_not_required_on_linux() -> None:
    """WSL checks must pass on Linux because it is not required."""
    platform = make_platform(OperatingSystem.LINUX, PackageManager.APT)
    runner = Runner(dry_run=True)
    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False):
        status = check_wsl(platform, runner)
    assert status.present is True


def test_check_wsl_present_when_running_inside_wsl() -> None:
    """WSL checks must pass when the script itself is running inside WSL."""
    platform = make_platform(OperatingSystem.LINUX, PackageManager.APT)
    runner = Runner(dry_run=True)
    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=True):
        status = check_wsl(platform, runner)
    assert status.present is True
    assert "inside WSL" in status.message


def test_check_wsl_missing_on_windows() -> None:
    """WSL checks must fail on Windows when WSL is unavailable."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = Runner(dry_run=True)
    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False):
        status = check_wsl(platform, runner)
    assert status.present is False


def test_check_all_returns_list() -> None:
    """check_all must return a list of PrerequisiteStatus objects."""
    platform = make_platform(detect_os(), PackageManager.UNKNOWN)
    runner = Runner(dry_run=True)
    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False):
        statuses = check_all(platform, runner)
    assert all(isinstance(s, PrerequisiteStatus) for s in statuses)


def test_ensure_wsl_tools_installs_agent_first_baseline() -> None:
    """WSL tool install should batch apt packages in one install script."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = SpyRunner()

    ensure_wsl_tools(cast(Runner, runner), platform)

    expected_packages = [
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
        "xh",
        "ast-grep",
        "sd",
        "git-delta",
        "typos",
        "uv",
    ]

    install_script_commands = [
        command
        for command in runner.commands
        if command[:2] == ["sh", "-c"] and "apt-get install -y" in command[-1]
    ]
    assert len(install_script_commands) == 1
    script = install_script_commands[0][-1]
    for package in expected_packages:
        assert package in script


def test_ensure_host_cli_extras_uses_agent_first_baseline_per_manager() -> None:
    """Host extras should install the same baseline with package-name mapping per manager."""
    expected = {
        PackageManager.APT: [
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
            "xh",
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
            "xh",
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
            "xh",
            "ast-grep",
            "sd",
            "git-delta",
            "typos",
            "uv",
        ],
    }

    for manager, expected_packages in expected.items():
        platform = make_platform(OperatingSystem.LINUX, manager)
        runner = SpyRunner()

        ensure_host_cli_extras(cast(Runner, runner), platform)

        assert _installed_packages(runner.commands, manager) == expected_packages


def test_ensure_host_cli_extras_noop_on_windows() -> None:
    """Windows host path should skip host extra package installation."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = SpyRunner()

    ensure_host_cli_extras(cast(Runner, runner), platform)

    assert runner.commands == []


def test_ensure_wsl_tools_runs_directly_when_inside_wsl() -> None:
    """When running inside WSL, ensure_wsl_tools should not wrap commands with wsl."""
    platform = make_platform(OperatingSystem.LINUX, PackageManager.APT)
    runner = SpyRunner()

    with (
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=True),
        mock.patch("terminal_setup.prerequisites._apt_package_available", return_value=True),
    ):
        ensure_wsl_tools(cast(Runner, runner), platform)

    install_script_commands = [
        command
        for command in runner.commands
        if command[:2] == ["sh", "-c"] and "apt-get install -y" in command[-1]
    ]
    assert len(install_script_commands) == 1
    assert "wsl" not in install_script_commands[0]


def test_system_version_policy_defaults() -> None:
    """The default policy must neither uninstall nor keep system versions."""
    policy = system_version_policy()
    assert policy.uninstall is False
    assert policy.keep is False


def test_find_system_command_path_detects_system_binary() -> None:
    """_find_system_command_path must return the path for a system binary."""
    runner = FakeRunner(
        outputs={
            ("sh", "-c", "command -v rg"): (0, "/usr/bin/rg"),
        }
    )
    assert find_system_command_path(cast(Runner, runner), "rg") == "/usr/bin/rg"


def test_find_system_command_path_ignores_user_local() -> None:
    """_find_system_command_path must ignore binaries under the user's home."""
    runner = FakeRunner(
        outputs={
            ("sh", "-c", "command -v rg"): (0, str(Path.home() / ".local/bin/rg")),
        }
    )
    assert find_system_command_path(cast(Runner, runner), "rg") is None


def test_find_system_command_path_uses_wsl_when_distro_is_provided() -> None:
    """_find_system_command_path must query the WSL distro when requested."""
    runner = FakeRunner(
        outputs={
            ("wsl", "-d", "Ubuntu", "--", "sh", "-c", "command -v rg"): (0, "/usr/bin/rg"),
        }
    )
    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False):
        path = find_system_command_path(cast(Runner, runner), "rg", wsl_distro="Ubuntu")
    assert path == "/usr/bin/rg"


def test_find_owning_package_apt() -> None:
    """_find_owning_package must parse dpkg -S output on apt systems."""
    runner = FakeRunner(
        outputs={
            ("dpkg", "-S", "/usr/bin/rg"): (0, "ripgrep: /usr/bin/rg"),
        }
    )
    package = find_owning_package(cast(Runner, runner), "/usr/bin/rg", PackageManager.APT)
    assert package == "ripgrep"


def test_find_owning_package_pacman() -> None:
    """_find_owning_package must parse pacman -Qo output."""
    runner = FakeRunner(
        outputs={
            ("pacman", "-Qo", "/usr/bin/rg"): (0, "/usr/bin/rg is owned by ripgrep 14.1.0-1"),
        }
    )
    package = find_owning_package(cast(Runner, runner), "/usr/bin/rg", PackageManager.PACMAN)
    assert package == "ripgrep"


def test_find_owning_package_dnf() -> None:
    """_find_owning_package must parse rpm -qf output."""
    runner = FakeRunner(
        outputs={
            ("rpm", "-qf", "/usr/bin/rg"): (0, "ripgrep-14.1.0-1.fc40.x86_64"),
        }
    )
    package = find_owning_package(cast(Runner, runner), "/usr/bin/rg", PackageManager.DNF)
    assert package == "ripgrep"


def test_warn_or_uninstall_keeps_system_version_when_requested() -> None:
    """With keep policy, the function must warn and not run any uninstall command."""
    runner = FakeRunner(
        outputs={
            ("sh", "-c", "command -v rg"): (0, "/usr/bin/rg"),
            ("dpkg", "-S", "/usr/bin/rg"): (0, "ripgrep: /usr/bin/rg"),
        }
    )
    warn_or_uninstall_system_version(
        cast(Runner, runner),
        "rg",
        PackageManager.APT,
        policy=SystemVersionPolicy(keep=True),
    )
    assert not any("apt-get" in " ".join(cmd) for cmd in runner.commands)


def test_warn_or_uninstall_removes_system_version_when_requested() -> None:
    """With uninstall policy, the function must run the package manager remove command."""
    runner = FakeRunner(
        outputs={
            ("sh", "-c", "command -v rg"): (0, "/usr/bin/rg"),
            ("dpkg", "-S", "/usr/bin/rg"): (0, "ripgrep: /usr/bin/rg"),
        }
    )
    warn_or_uninstall_system_version(
        cast(Runner, runner),
        "rg",
        PackageManager.APT,
        policy=SystemVersionPolicy(uninstall=True),
    )
    assert ["sudo", "apt-get", "remove", "-y", "ripgrep"] in runner.commands


def test_warn_or_uninstall_prompts_and_removes_on_yes() -> None:
    """Interactive mode must remove the package when the user answers yes."""
    runner = FakeRunner(
        outputs={
            ("sh", "-c", "command -v rg"): (0, "/usr/bin/rg"),
            ("dpkg", "-S", "/usr/bin/rg"): (0, "ripgrep: /usr/bin/rg"),
        }
    )
    runner.confirm_answer = True
    warn_or_uninstall_system_version(cast(Runner, runner), "rg", PackageManager.APT)
    assert len(runner.confirm_prompts) == 1
    assert "Remove the system version" in runner.confirm_prompts[0]
    assert ["sudo", "apt-get", "remove", "-y", "ripgrep"] in runner.commands


def test_warn_or_uninstall_prompts_and_keeps_on_no() -> None:
    """Interactive mode must keep the package when the user answers no."""
    runner = FakeRunner(
        outputs={
            ("sh", "-c", "command -v rg"): (0, "/usr/bin/rg"),
            ("dpkg", "-S", "/usr/bin/rg"): (0, "ripgrep: /usr/bin/rg"),
        }
    )
    runner.confirm_answer = False
    warn_or_uninstall_system_version(cast(Runner, runner), "rg", PackageManager.APT)
    assert len(runner.confirm_prompts) == 1
    assert ["sudo", "apt-get", "remove", "-y", "ripgrep"] not in runner.commands


def test_ensure_wsl_tools_no_sudo_checks_target_wsl_when_called_from_windows() -> None:
    """No-sudo WSL setup launched on Windows must check/install against the WSL distro."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = FakeRunner()

    with (
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch(
            "terminal_setup.prerequisites._command_available",
            return_value=True,
        ) as available,
        mock.patch(
            "terminal_setup.prerequisites._is_user_local_command_available",
            return_value=True,
        ) as user_local,
    ):
        ensure_wsl_tools(cast(Runner, runner), platform, no_sudo=True)

    assert available.call_count >= 1
    assert all(call.kwargs.get("wsl_distro") == "Ubuntu" for call in available.call_args_list)
    assert user_local.call_count >= 1
    assert all(call.kwargs.get("wsl_distro") == "Ubuntu" for call in user_local.call_args_list)
