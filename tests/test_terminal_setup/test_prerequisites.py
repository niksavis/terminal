"""Tests for prerequisite checking and installation helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast
from unittest import mock

from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo, detect_os
from terminal_setup.prerequisites import (
    TARGET_NODE_MAJOR,
    PrerequisiteStatus,
    SystemVersionPolicy,
    check_all,
    check_command,
    check_package_manager,
    check_wsl,
    ensure_host_cli_extras,
    ensure_node,
    ensure_wsl_tools,
    install_package,
    windows_tool_candidate_dirs,
)
from terminal_setup.prerequisites import (
    _command_available as command_available,
)
from terminal_setup.prerequisites import (
    _find_owning_package as find_owning_package,
)
from terminal_setup.prerequisites import (
    _find_system_command_path as find_system_command_path,
)
from terminal_setup.prerequisites import (
    _install_lazygit_release as install_lazygit_release,
)
from terminal_setup.prerequisites import (
    _reconcile_system_versions as reconcile_system_versions,
)
from terminal_setup.prerequisites import (
    _system_version_policy as system_version_policy,
)
from terminal_setup.prerequisites import (
    _warn_or_uninstall_system_version as warn_or_uninstall_system_version,
)
from terminal_setup.prerequisites import (
    _wsl_apt_install_script as wsl_apt_install_script,
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
        self.dry_run = False
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
        """Record a command and return a successful completed process."""
        del check, dry_run_safe, interactive, cwd, env
        self.commands.append(command)
        script = command[-1] if len(command) >= 3 and command[0] in {"sh", "wsl"} else ""
        if "jesseduffield/lazygit/releases/latest" in script:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="0.49.0\n",
                stderr="",
            )
        if "lazygit --version" in script:
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
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

    def success(self, message: str) -> None:
        """Record a success message."""
        self.messages.append(("success", message))

    def step(self, message: str) -> None:
        """Record a step message."""
        self.messages.append(("step", message))

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


def test_command_available_uses_user_local_bin_when_launched_from_windows() -> None:
    """Windows->WSL checks should see binaries in ~/.local/bin even if PATH misses them."""
    runner = FakeRunner(
        outputs={
            (
                "wsl",
                "-d",
                "Ubuntu",
                "--exec",
                "sh",
                "-c",
                "if test -x ~/.local/bin/uv; then exit 0; fi; command -v uv >/dev/null 2>&1",
            ): (0, ""),
        }
    )
    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False):
        assert command_available(cast(Runner, runner), "uv", wsl_distro="Ubuntu") is True


def test_wsl_apt_install_script_removes_legacy_wezterm_repo() -> None:
    """WSL apt install script should remove legacy fury.wez.dev source entries."""
    script = wsl_apt_install_script(["zsh", "tmux"])
    assert "rm -f /etc/apt/sources.list.d/wezterm.list" in script
    assert "fury\\\\.wez\\\\.dev" in script
    assert "apt\\\\.fury\\\\.io/wez" in script
    assert "/etc/apt/sources.list.d/*" in script
    assert 'rm -f "$file"' in script
    assert 'sed -i "/fury\\\\.wez\\\\.dev/d;/apt\\\\.fury\\\\.io\\\\/wez/d"' in script
    assert "apt-get update" in script
    assert "apt-get install -y zsh tmux" in script


def test_ensure_wsl_tools_installs_agent_first_baseline() -> None:
    """WSL tool install should batch apt packages in one install script."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = SpyRunner()

    with (
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=True),
        mock.patch("terminal_setup.prerequisites._require_interactive_stdin_for_sudo"),
    ):
        ensure_wsl_tools(cast(Runner, runner), platform)

    expected_packages = [
        "zsh",
        "tmux",
        "git",
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

    install_script_commands = [
        command
        for command in runner.commands
        if command[:2] == ["sh", "-c"] and "apt-get install -y" in command[-1]
    ]
    assert len(install_script_commands) == 1
    script = install_script_commands[0][-1]
    for package in expected_packages:
        assert package in script

    lazygit_release_commands = [
        command
        for command in runner.commands
        if command[:2] == ["sh", "-c"] and "jesseduffield/lazygit/releases/latest" in command[-1]
    ]
    assert len(lazygit_release_commands) == 1


def test_ensure_host_cli_extras_uses_agent_first_baseline_per_manager() -> None:
    """Host extras should install the same baseline with package-name mapping per manager."""
    expected = {
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

    for manager, expected_packages in expected.items():
        platform = make_platform(OperatingSystem.LINUX, manager)
        runner = SpyRunner()

        ensure_host_cli_extras(cast(Runner, runner), platform)

        assert _installed_packages(runner.commands, manager) == expected_packages
        assert any(
            command[:2] == ["sh", "-c"] and "jesseduffield/lazygit/releases/latest" in command[-1]
            for command in runner.commands
        )


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
        mock.patch("terminal_setup.prerequisites._require_interactive_stdin_for_sudo"),
    ):
        ensure_wsl_tools(cast(Runner, runner), platform)

    install_script_commands = [
        command
        for command in runner.commands
        if command[:2] == ["sh", "-c"] and "apt-get install -y" in command[-1]
    ]
    assert len(install_script_commands) == 1
    assert "wsl" not in install_script_commands[0]


def test_install_lazygit_release_skips_when_up_to_date() -> None:
    """Release install should skip when installed lazygit matches latest version."""
    latest_query = (
        "curl -fsSL https://api.github.com/repos/jesseduffield/lazygit/releases/latest "
        '| sed -n \'s/.*"tag_name": *"v\\([^"]*\\)".*/\\1/p\' | head -n 1'
    )
    installed_query = (
        'PATH="$HOME/.local/bin:$PATH"; '
        "if ! command -v lazygit >/dev/null 2>&1; then exit 0; fi; "
        "lazygit --version 2>/dev/null "
        "| grep -Eo 'version=[0-9][0-9.]*' | head -n 1 | cut -d= -f2"
    )
    runner = FakeRunner(
        outputs={
            ("sh", "-c", latest_query): (0, "0.49.0\n"),
            ("sh", "-c", installed_query): (0, "0.49.0\n"),
        }
    )

    install_lazygit_release(cast(Runner, runner), no_sudo=False)

    assert any("releases/latest" in command[-1] for command in runner.commands)
    assert any("lazygit --version" in command[-1] for command in runner.commands)
    assert not any(
        "releases/download" in command[-1] and "tar.gz" in command[-1]
        for command in runner.commands
    )


def test_install_lazygit_release_uses_first_version_token() -> None:
    """Lazygit installed-version parsing must use the first version token."""
    latest_query = (
        "curl -fsSL https://api.github.com/repos/jesseduffield/lazygit/releases/latest "
        '| sed -n \'s/.*"tag_name": *"v\\([^"]*\\)".*/\\1/p\' | head -n 1'
    )
    installed_query = (
        'PATH="$HOME/.local/bin:$PATH"; '
        "if ! command -v lazygit >/dev/null 2>&1; then exit 0; fi; "
        "lazygit --version 2>/dev/null "
        "| grep -Eo 'version=[0-9][0-9.]*' | head -n 1 | cut -d= -f2"
    )
    runner = FakeRunner(
        outputs={
            ("sh", "-c", latest_query): (0, "0.63.0\n"),
            (
                "sh",
                "-c",
                installed_query,
            ): (
                0,
                "0.43.0\n",
            ),
        }
    )
    runner.confirm_answer = False

    install_lazygit_release(cast(Runner, runner), no_sudo=False)

    assert runner.confirm_prompts == ["Update lazygit from 0.43.0 to 0.63.0?"]


def test_install_package_apt_skips_when_up_to_date() -> None:
    """Apt installs should be skipped when installed and candidate versions match."""
    runner = FakeRunner(
        outputs={
            ("apt-cache", "show", "ripgrep"): (0, ""),
            (
                "apt-cache",
                "policy",
                "ripgrep",
            ): (
                0,
                "Installed: 14.0.3-1\nCandidate: 14.0.3-1\n",
            ),
        }
    )

    install_package(cast(Runner, runner), PackageManager.APT, "ripgrep")

    assert ["sudo", "apt-get", "install", "-y", "ripgrep"] not in runner.commands


def test_install_package_apt_prompts_on_update_and_installs_when_yes() -> None:
    """Apt installs should prompt on updates and proceed when the user confirms."""
    runner = FakeRunner(
        outputs={
            ("apt-cache", "show", "ripgrep"): (0, ""),
            (
                "apt-cache",
                "policy",
                "ripgrep",
            ): (
                0,
                "Installed: 13.0.0-1\nCandidate: 14.0.3-1\n",
            ),
        }
    )
    runner.confirm_answer = True

    install_package(cast(Runner, runner), PackageManager.APT, "ripgrep")

    assert ["sudo", "apt-get", "install", "-y", "ripgrep"] in runner.commands
    assert runner.confirm_prompts == ["Update ripgrep from 13.0.0-1 to 14.0.3-1?"]


def test_install_package_apt_prompts_on_update_and_skips_when_no() -> None:
    """Apt installs should prompt on updates and skip when the user declines."""
    runner = FakeRunner(
        outputs={
            ("apt-cache", "show", "ripgrep"): (0, ""),
            (
                "apt-cache",
                "policy",
                "ripgrep",
            ): (
                0,
                "Installed: 13.0.0-1\nCandidate: 14.0.3-1\n",
            ),
        }
    )
    runner.confirm_answer = False

    install_package(cast(Runner, runner), PackageManager.APT, "ripgrep")

    assert ["sudo", "apt-get", "install", "-y", "ripgrep"] not in runner.commands
    assert runner.confirm_prompts == ["Update ripgrep from 13.0.0-1 to 14.0.3-1?"]


def test_install_lazygit_release_prompts_on_update_and_skips_when_no() -> None:
    """Lazygit update should ask for consent and skip when user declines."""
    latest_query = (
        "curl -fsSL https://api.github.com/repos/jesseduffield/lazygit/releases/latest "
        '| sed -n \'s/.*"tag_name": *"v\\([^"]*\\)".*/\\1/p\' | head -n 1'
    )
    installed_query = (
        'PATH="$HOME/.local/bin:$PATH"; '
        "if ! command -v lazygit >/dev/null 2>&1; then exit 0; fi; "
        "lazygit --version 2>/dev/null "
        "| grep -Eo 'version=[0-9][0-9.]*' | head -n 1 | cut -d= -f2"
    )
    runner = FakeRunner(
        outputs={
            ("sh", "-c", latest_query): (0, "0.49.0\n"),
            ("sh", "-c", installed_query): (0, "0.48.0\n"),
        }
    )
    runner.confirm_answer = False

    install_lazygit_release(cast(Runner, runner), no_sudo=False)

    assert runner.confirm_prompts == ["Update lazygit from 0.48.0 to 0.49.0?"]
    assert not any(
        "releases/download" in command[-1] and "tar.gz" in command[-1]
        for command in runner.commands
    )


def test_install_lazygit_release_wraps_wsl_commands_with_exec() -> None:
    """Windows->WSL commands must use `wsl --exec` to avoid shell re-parsing.

    Without --exec the guest's default shell expands $variables inside the
    install script before sh runs, breaking the OS/arch detection.
    """
    latest_query = (
        "curl -fsSL https://api.github.com/repos/jesseduffield/lazygit/releases/latest "
        '| sed -n \'s/.*"tag_name": *"v\\([^"]*\\)".*/\\1/p\' | head -n 1'
    )
    runner = FakeRunner(
        outputs={
            ("wsl", "-d", "Ubuntu", "--exec", "sh", "-c", latest_query): (0, "0.63.0\n"),
        }
    )

    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False):
        install_lazygit_release(cast(Runner, runner), wsl_distro="Ubuntu", no_sudo=True)

    wsl_commands = [command for command in runner.commands if command[0] == "wsl"]
    assert wsl_commands
    assert all(command[:4] == ["wsl", "-d", "Ubuntu", "--exec"] for command in wsl_commands)
    install_scripts = [
        command[-1]
        for command in runner.commands
        if "releases/download" in command[-1] and "tar.gz" in command[-1]
    ]
    assert install_scripts
    assert "~/.local/bin/lazygit" in install_scripts[0]
    assert "sudo" not in install_scripts[0]


def test_ensure_node_installs_target_major_in_wsl_when_missing() -> None:
    """On Windows, ensure_node installs the target Node major into the WSL guest."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = SpyRunner()

    with (
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch(
            "terminal_setup.prerequisites._is_user_local_command_available",
            return_value=False,
        ),
    ):
        ensure_node(cast(Runner, runner), platform)

    install_scripts = [c[-1] for c in runner.commands if "nodejs.org/dist" in c[-1]]
    assert install_scripts
    assert f'"version":"v{TARGET_NODE_MAJOR}' in install_scripts[0]
    assert all(c[:4] == ["wsl", "-d", "Ubuntu", "--exec"] for c in runner.commands if c[0] == "wsl")


def test_ensure_node_skips_when_already_present() -> None:
    """ensure_node must not reinstall Node when it is already available."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = SpyRunner()

    with (
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch(
            "terminal_setup.prerequisites._is_user_local_command_available",
            return_value=True,
        ),
    ):
        ensure_node(cast(Runner, runner), platform)

    assert not any("nodejs.org/dist" in c[-1] for c in runner.commands)


def test_reconcile_removes_unowned_userlocal_duplicate() -> None:
    """A user-local tool with an unowned /usr/local system copy is removed."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.APT)
    runner = FakeRunner(
        outputs={
            (
                "wsl",
                "-d",
                "Ubuntu",
                "--exec",
                "sh",
                "-c",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
                "command -v lazygit",
            ): (0, "/usr/local/bin/lazygit"),
        }
    )
    policy = system_version_policy(uninstall_system_versions=True)

    def fake_user_local(_runner: object, binary: str, **_kwargs: object) -> bool:
        return binary == "lazygit"

    with (
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites._require_interactive_stdin_for_sudo"),
        mock.patch(
            "terminal_setup.prerequisites._is_user_local_command_available",
            side_effect=fake_user_local,
        ),
        mock.patch(
            "terminal_setup.prerequisites._find_owning_package",
            return_value=None,
        ),
    ):
        reconcile_system_versions(cast(Runner, runner), platform, policy, wsl_distro="Ubuntu")

    assert [
        "wsl",
        "-d",
        "Ubuntu",
        "--exec",
        "sudo",
        "rm",
        "-f",
        "/usr/local/bin/lazygit",
    ] in runner.commands


def test_reconcile_skips_tools_without_userlocal_copy() -> None:
    """Reconcile must not touch tools that have no user-local copy."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.APT)
    runner = FakeRunner()
    policy = system_version_policy(uninstall_system_versions=True)

    with (
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites._require_interactive_stdin_for_sudo"),
        mock.patch(
            "terminal_setup.prerequisites._is_user_local_command_available",
            return_value=False,
        ),
    ):
        reconcile_system_versions(cast(Runner, runner), platform, policy, wsl_distro="Ubuntu")

    assert not any("rm" in command for command in runner.commands)


def test_windows_tool_candidate_dirs_cover_user_programs() -> None:
    """Candidate dirs must include the per-user programs directory."""
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    wezterm_dirs = windows_tool_candidate_dirs(platform, "wezterm")
    starship_dirs = windows_tool_candidate_dirs(platform, "starship")
    assert platform.user_programs_dir / "WezTerm" in wezterm_dirs
    assert platform.user_programs_dir / "starship" in starship_dirs
    assert windows_tool_candidate_dirs(platform, "unknown-tool") == []


def test_system_version_policy_defaults() -> None:
    """The default policy must neither uninstall nor keep system versions."""
    policy = system_version_policy()
    assert policy.uninstall is False
    assert policy.keep is False


def test_find_system_command_path_detects_system_binary() -> None:
    """_find_system_command_path must return the path for a system binary."""
    runner = FakeRunner(
        outputs={
            (
                "sh",
                "-c",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin command -v rg",
            ): (0, "/usr/bin/rg"),
        }
    )
    assert find_system_command_path(cast(Runner, runner), "rg") == "/usr/bin/rg"


def test_find_system_command_path_ignores_user_local() -> None:
    """_find_system_command_path must ignore binaries under the user's home."""
    runner = FakeRunner(
        outputs={
            (
                "sh",
                "-c",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin command -v rg",
            ): (0, str(Path.home() / ".local/bin/rg")),
        }
    )
    assert find_system_command_path(cast(Runner, runner), "rg") is None


def test_find_system_command_path_uses_wsl_when_distro_is_provided() -> None:
    """_find_system_command_path must query the WSL distro when requested."""
    runner = FakeRunner(
        outputs={
            (
                "wsl",
                "-d",
                "Ubuntu",
                "--exec",
                "sh",
                "-c",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin command -v rg",
            ): (0, "/usr/bin/rg"),
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
            (
                "sh",
                "-c",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin command -v rg",
            ): (0, "/usr/bin/rg"),
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
            (
                "sh",
                "-c",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin command -v rg",
            ): (0, "/usr/bin/rg"),
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
            (
                "sh",
                "-c",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin command -v rg",
            ): (0, "/usr/bin/rg"),
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
            (
                "sh",
                "-c",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin command -v rg",
            ): (0, "/usr/bin/rg"),
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
            "terminal_setup.prerequisites._install_lazygit_release",
            return_value=None,
        ),
    ):
        ensure_wsl_tools(cast(Runner, runner), platform, no_sudo=True)

    assert available.call_count >= 1
    assert all(call.kwargs.get("wsl_distro") == "Ubuntu" for call in available.call_args_list)
