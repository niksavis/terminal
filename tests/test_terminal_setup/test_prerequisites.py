from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast
from unittest import mock

import pytest

from terminal_setup import release_install
from terminal_setup.platform import (
    OperatingSystem,
    PackageManager,
    PlatformInfo,
    detect_os,
    wsl_exec_command,
)
from terminal_setup.prerequisites import (
    _RECONCILE_BINARIES,
    LAZYGIT_LATEST_QUERY,
    RELEASE_TOOLS,
    TARGET_NODE_MAJOR,
    PrerequisiteStatus,
    SystemVersionPolicy,
    _add_to_user_path,
    check_all,
    check_command,
    check_package_manager,
    check_wsl,
    ensure_host_cli_extras,
    ensure_node,
    ensure_starship,
    ensure_wsl_system_packages,
    ensure_wsl_tools,
    install_package,
    missing_wsl_system_packages,
    windows_tool_candidate_dirs,
    wsl_system_packages_command,
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
    _install_user_local_tool as install_user_local_tool,
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

RELEASE_INSTALL_SOURCE = Path(release_install.__file__).read_text(encoding="utf-8")


def make_platform(os: OperatingSystem, package_manager: PackageManager) -> PlatformInfo:
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
    def __init__(self) -> None:
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
        label: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check, dry_run_safe, interactive, cwd, env, label
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
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def info(self, message: str) -> None:
        self.messages.append(("info", message))

    def warn(self, message: str) -> None:
        self.messages.append(("warn", message))

    def error(self, message: str) -> None:
        self.messages.append(("error", message))

    def success(self, message: str) -> None:
        self.messages.append(("success", message))

    def step(self, message: str) -> None:
        self.messages.append(("step", message))

    def prompt(self, message: str) -> None:
        self.messages.append(("prompt", message))

    def command(self, command: list[str], label: str | None = None) -> None:
        self.messages.append(("command", label or " ".join(command)))

    def confirm(self, message: str) -> bool:
        self.messages.append(("confirm", message))
        return False


class FakeRunner:
    def __init__(self, outputs: dict[tuple[str, ...], tuple[int, str]] | None = None) -> None:
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
        label: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check, dry_run_safe, interactive, cwd, env, label
        self.commands.append(command)
        key = tuple(command)
        returncode, stdout = self.outputs.get(key, (0, ""))
        return subprocess.CompletedProcess(args=command, returncode=returncode, stdout=stdout)

    def which(self, _command: str) -> str | None:
        return None

    def confirm(self, prompt: str) -> bool:
        self.confirm_prompts.append(prompt)
        return self.confirm_answer


def _installed_packages(commands: list[list[str]], manager: PackageManager) -> list[str]:
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
    runner = Runner(dry_run=True)
    status = check_command(runner, "python", "python")
    assert status.present is True
    assert "python" in status.message


def test_check_command_missing_command() -> None:
    runner = Runner(dry_run=True)
    status = check_command(runner, "not-a-real-tool", "not-a-real-tool-xyz")
    assert status.present is False


def test_check_package_manager_unknown() -> None:
    platform = make_platform(OperatingSystem.LINUX, PackageManager.UNKNOWN)
    status = check_package_manager(platform)
    assert status.present is False


def test_check_package_manager_known() -> None:
    platform = make_platform(OperatingSystem.LINUX, PackageManager.APT)
    status = check_package_manager(platform)
    assert status.present is True


def test_check_wsl_not_required_on_linux() -> None:
    platform = make_platform(OperatingSystem.LINUX, PackageManager.APT)
    runner = Runner(dry_run=True)
    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False):
        status = check_wsl(platform, runner)
    assert status.present is True


def test_check_wsl_present_when_running_inside_wsl() -> None:
    platform = make_platform(OperatingSystem.LINUX, PackageManager.APT)
    runner = Runner(dry_run=True)
    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=True):
        status = check_wsl(platform, runner)
    assert status.present is True
    assert "inside WSL" in status.message


def test_check_wsl_missing_on_windows() -> None:
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = Runner(dry_run=True)
    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False):
        status = check_wsl(platform, runner)
    assert status.present is False


def test_check_all_returns_list() -> None:
    platform = make_platform(detect_os(), PackageManager.UNKNOWN)
    runner = Runner(dry_run=True)
    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False):
        statuses = check_all(platform, runner)
    assert all(isinstance(s, PrerequisiteStatus) for s in statuses)


def test_command_available_uses_user_local_bin_when_launched_from_windows() -> None:
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
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = SpyRunner()

    ensure_host_cli_extras(cast(Runner, runner), platform)

    assert runner.commands == []


def test_ensure_wsl_tools_runs_directly_when_inside_wsl() -> None:
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
    latest_query = LAZYGIT_LATEST_QUERY
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
    latest_query = LAZYGIT_LATEST_QUERY
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
    latest_query = LAZYGIT_LATEST_QUERY
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

    latest_query = LAZYGIT_LATEST_QUERY
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


def test_reconcile_uses_apt_for_wsl_from_windows() -> None:
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = FakeRunner()
    policy = system_version_policy(uninstall_system_versions=True)

    def fake_user_local(_runner: object, binary: str, **_kwargs: object) -> bool:
        return binary == "git-lfs"

    def fake_system_path(_runner: object, command: str, **_kwargs: object) -> str | None:
        return "/usr/bin/git-lfs" if command == "git-lfs" else None

    with (
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites._require_interactive_stdin_for_sudo"),
        mock.patch(
            "terminal_setup.prerequisites._is_user_local_command_available",
            side_effect=fake_user_local,
        ),
        mock.patch(
            "terminal_setup.prerequisites._find_system_command_path",
            side_effect=fake_system_path,
        ),
        mock.patch(
            "terminal_setup.prerequisites._find_owning_package",
            return_value="git-lfs",
        ) as owning,
    ):
        reconcile_system_versions(cast(Runner, runner), platform, policy, wsl_distro="Ubuntu")

    assert owning.call_args.args[2] == PackageManager.APT
    assert [
        "wsl",
        "-d",
        "Ubuntu",
        "--exec",
        "sudo",
        "apt-get",
        "remove",
        "-y",
        "git-lfs",
    ] in runner.commands


def test_windows_tool_candidate_dirs_cover_user_programs() -> None:
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    wezterm_dirs = windows_tool_candidate_dirs(platform, "wezterm")
    starship_dirs = windows_tool_candidate_dirs(platform, "starship")
    assert platform.user_programs_dir / "WezTerm" in wezterm_dirs
    assert platform.user_programs_dir / "starship" in starship_dirs
    assert windows_tool_candidate_dirs(platform, "unknown-tool") == []


def test_system_version_policy_defaults() -> None:
    policy = system_version_policy()
    assert policy.uninstall is False
    assert policy.keep is False


def test_find_system_command_path_detects_system_binary() -> None:
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
    runner = FakeRunner(
        outputs={
            ("dpkg", "-S", "/usr/bin/rg"): (0, "ripgrep: /usr/bin/rg"),
        }
    )
    package = find_owning_package(cast(Runner, runner), "/usr/bin/rg", PackageManager.APT)
    assert package == "ripgrep"


def test_find_owning_package_pacman() -> None:
    runner = FakeRunner(
        outputs={
            ("pacman", "-Qo", "/usr/bin/rg"): (0, "/usr/bin/rg is owned by ripgrep 14.1.0-1"),
        }
    )
    package = find_owning_package(cast(Runner, runner), "/usr/bin/rg", PackageManager.PACMAN)
    assert package == "ripgrep"


def test_find_owning_package_dnf() -> None:
    runner = FakeRunner(
        outputs={
            ("rpm", "-qf", "/usr/bin/rg"): (0, "ripgrep-14.1.0-1.fc40.x86_64"),
        }
    )
    package = find_owning_package(cast(Runner, runner), "/usr/bin/rg", PackageManager.DNF)
    assert package == "ripgrep"


def test_warn_or_uninstall_keeps_system_version_when_requested() -> None:
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


def test_install_user_local_tool_downloads_every_release_tool_through_the_installer() -> None:
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)

    for package, (repo, binary, patterns) in RELEASE_TOOLS.items():
        runner = SpyRunner()
        with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=True):
            handled = install_user_local_tool(cast(Runner, runner), package, platform, update=True)

        assert handled is True
        assert runner.commands == [
            ["python3", "-I", "-c", RELEASE_INSTALL_SOURCE, repo, binary, "1", *patterns]
        ]


def test_reconcile_binaries_include_gitlfs_and_direnv() -> None:
    assert "git-lfs" in _RECONCILE_BINARIES
    assert "direnv" in _RECONCILE_BINARIES


def test_ensure_starship_installs_into_wsl_guest_from_windows() -> None:
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    runner = SpyRunner()
    original_run = runner.run

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        result = original_run(command, **kwargs)  # type: ignore[arg-type]
        script = command[-1]
        if "test -x ~/.local/bin/starship" in script or "command -v starship" in script:
            return subprocess.CompletedProcess(command, 1, "", "")
        return result

    runner.run = run  # type: ignore[method-assign]
    runner.which = lambda _command: "C:/Program Files/starship/bin/starship.exe"  # type: ignore[attr-defined]

    with mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False):
        ensure_starship(cast(Runner, runner), platform)

    scripts = [command[-1] for command in runner.commands if command[:1] != ["powershell"]]
    assert any("starship.rs/install.sh" in script for script in scripts), (
        "expected a WSL guest starship install"
    )


def test_add_to_user_path_preserves_unexpanded_entries_and_is_idempotent() -> None:

    runner = SpyRunner()
    with mock.patch("terminal_setup.prerequisites._add_to_process_path"):
        _add_to_user_path(cast(Runner, runner), Path("C:/Users/test/tool"))

    script = runner.commands[-1][-1]
    assert "DoNotExpandEnvironmentNames" in script
    assert "ExpandString" in script
    assert "-ieq" in script
    assert "$dir = 'C:\\Users\\test\\tool'" in script
    assert "SendMessageTimeout" in script


def test_ensure_wsl_tools_update_reinstalls_existing_user_local_tools() -> None:
    platform = make_platform(OperatingSystem.LINUX, PackageManager.APT)
    runner = SpyRunner()
    installed: list[str] = []
    with (
        mock.patch(
            "terminal_setup.prerequisites._is_user_local_command_available",
            return_value=True,
        ),
        mock.patch(
            "terminal_setup.prerequisites._command_available",
            return_value=True,
        ),
        mock.patch(
            "terminal_setup.prerequisites._install_user_local_tool",
            side_effect=lambda _runner, package, _platform, **_kwargs: (
                installed.append(package) or True
            ),
        ),
        mock.patch("terminal_setup.prerequisites._reconcile_system_versions"),
    ):
        ensure_wsl_tools(cast(Runner, runner), platform, no_sudo=True, update=False)
        assert set(installed) == {"lazygit", *RELEASE_TOOLS}
        installed.clear()
        ensure_wsl_tools(cast(Runner, runner), platform, no_sudo=True, update=True)
    assert "fzf" in installed
    assert "jq" in installed
    assert len(installed) > 10


def _dpkg_state(installed: set[str], *, docker_command: bool = False):
    def dpkg(_runner: object, package: str, *, wsl_distro: str | None) -> bool:
        del wsl_distro
        return package in installed

    def available(_runner: object, command: str, *, wsl_distro: str | None = None) -> bool:
        del wsl_distro
        return docker_command and command == "docker"

    return (
        mock.patch("terminal_setup.prerequisites._dpkg_installed", side_effect=dpkg),
        mock.patch("terminal_setup.prerequisites._command_available", side_effect=available),
    )


def test_missing_system_packages_on_a_fresh_image_include_podman_docker() -> None:
    dpkg, available = _dpkg_state(set())
    with dpkg, available:
        missing = missing_wsl_system_packages(cast(Runner, SpyRunner()), wsl_distro="Ubuntu")

    assert missing == ["zsh", "tree", "podman", "bubblewrap", "socat", "podman-docker"]


@pytest.mark.parametrize(
    ("installed", "docker_command"),
    [({"docker.io"}, False), ({"docker-ce-cli"}, False), (set(), True)],
)
def test_podman_docker_is_left_out_when_docker_is_present(
    installed: set[str], *, docker_command: bool
) -> None:
    dpkg, available = _dpkg_state(installed, docker_command=docker_command)
    with dpkg, available:
        missing = missing_wsl_system_packages(cast(Runner, SpyRunner()), wsl_distro="Ubuntu")

    assert "podman-docker" not in missing
    assert "podman" in missing


def test_system_packages_command_updates_and_upgrades_before_installing() -> None:
    assert wsl_system_packages_command(["zsh", "podman"]) == (
        "sudo apt-get update && sudo apt-get upgrade -y && sudo apt-get install -y zsh podman"
    )


def _run_system_packages(
    *, allow_sudo: bool, assume_yes: bool, answer: bool, tty: bool
) -> SpyRunner:
    runner = SpyRunner()
    runner.confirm = lambda _message: answer  # type: ignore[attr-defined]
    platform = make_platform(OperatingSystem.WINDOWS, PackageManager.WINGET)
    dpkg, available = _dpkg_state({"zsh", "tree", "podman", "bubblewrap", "docker.io"})
    with (
        dpkg,
        available,
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites.sys.stdin.isatty", return_value=tty),
    ):
        ensure_wsl_system_packages(
            cast(Runner, runner), platform, allow_sudo=allow_sudo, assume_yes=assume_yes
        )
    return runner


def test_system_packages_run_after_the_user_agrees() -> None:
    runner = _run_system_packages(allow_sudo=True, assume_yes=False, answer=True, tty=True)

    assert runner.commands == [
        wsl_exec_command("Ubuntu", ["sh", "-c", wsl_system_packages_command(["socat"])])
    ]


@pytest.mark.parametrize(
    ("allow_sudo", "answer", "tty"),
    [(True, False, True), (True, True, False), (False, True, True)],
)
def test_system_packages_print_the_command_when_declined_or_not_allowed(
    *, allow_sudo: bool, answer: bool, tty: bool
) -> None:
    runner = _run_system_packages(allow_sudo=allow_sudo, assume_yes=False, answer=answer, tty=tty)

    assert runner.commands == []
    assert ("step", f"To add them, run this in WSL: {wsl_system_packages_command(['socat'])}") in (
        runner.reporter.messages
    )


def test_system_install_runs_the_packages_without_asking() -> None:
    runner = _run_system_packages(allow_sudo=True, assume_yes=True, answer=False, tty=False)

    assert len(runner.commands) == 1
