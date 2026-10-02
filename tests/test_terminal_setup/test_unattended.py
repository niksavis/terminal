from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

import pytest

from terminal_setup import configs, prerequisites
from terminal_setup.cli import build_parser
from terminal_setup.platform import (
    OperatingSystem,
    PackageManager,
    PlatformInfo,
    wsl_exec_command,
    wsl_root_exec_command,
)
from terminal_setup.runner import Runner

from .test_runner import CapturingReporter


@dataclass
class RecordingRunner(Runner):
    outputs: dict[tuple[str, ...], tuple[int, str]] = field(default_factory=dict)
    commands: list[list[str]] = field(default_factory=list)
    has_sudo: bool = True

    def run(  # noqa: PLR0913
        self,
        command: list[str],
        *,
        check: bool = True,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        interactive: bool = False,
        dry_run_safe: bool = False,
        label: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check, cwd, env, interactive, dry_run_safe, label
        self.commands.append(command)
        returncode, stdout = self.outputs.get(tuple(command), (0, ""))
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    def which(self, command: str) -> str | None:
        if command == "sudo" and self.has_sudo:
            return "/usr/bin/sudo"
        return None


def _windows_platform() -> PlatformInfo:
    return PlatformInfo(
        os=OperatingSystem.WINDOWS,
        package_manager=PackageManager.WINGET,
        is_wsl_available=True,
        is_wsl_default_debian_family=True,
        wsl_distribution="Ubuntu",
        shell="pwsh",
        home=Path.home(),
        wezterm_config_dir=None,
        vscode_settings_path=None,
    )


def _unattended_runner(**kwargs: object) -> RecordingRunner:
    return RecordingRunner(reporter=CapturingReporter(), unattended=True, **kwargs)  # type: ignore[arg-type]


def test_unattended_confirm_answers_no_without_asking() -> None:
    reporter = CapturingReporter()
    runner = Runner(reporter=reporter, unattended=True)

    assert runner.confirm("Remove the system version?") is False
    assert not [message for message in reporter.messages if message[0] == "confirm"]
    assert ("prompt", "Remove the system version? (answer 'no' in unattended mode)") in (
        reporter.messages
    )


def test_unattended_flag_is_parsed() -> None:
    assert build_parser().parse_args(["--unattended"]).unattended is True
    assert build_parser().parse_args([]).unattended is False


def _ensure_packages(runner: RecordingRunner, *, in_wsl: bool) -> None:
    with (
        mock.patch.object(prerequisites, "missing_wsl_system_packages", return_value=["zsh"]),
        mock.patch.object(prerequisites, "is_running_in_wsl", return_value=in_wsl),
    ):
        prerequisites.ensure_wsl_system_packages(
            runner, _windows_platform(), allow_sudo=True, assume_yes=False
        )


def test_unattended_windows_host_installs_system_packages_as_wsl_root() -> None:
    runner = _unattended_runner()

    _ensure_packages(runner, in_wsl=False)

    script = prerequisites.wsl_system_packages_root_script(["zsh"])
    assert runner.commands == [wsl_root_exec_command("Ubuntu", ["sh", "-c", script])]
    assert "sudo" not in script


def test_unattended_inside_wsl_uses_passwordless_sudo() -> None:
    runner = _unattended_runner()

    _ensure_packages(runner, in_wsl=True)

    script = prerequisites.wsl_system_packages_root_script(["zsh"])
    assert runner.commands == [["sudo", "-n", "true"], ["sudo", "-n", "sh", "-c", script]]


@pytest.mark.parametrize("has_sudo", [True, False])
def test_unattended_inside_wsl_prints_the_command_when_sudo_needs_a_password(
    *, has_sudo: bool
) -> None:
    runner = _unattended_runner(has_sudo=has_sudo, outputs={("sudo", "-n", "true"): (1, "")})

    _ensure_packages(runner, in_wsl=True)

    assert runner.commands == ([["sudo", "-n", "true"]] if has_sudo else [])
    command = prerequisites.wsl_system_packages_command(["zsh"])
    assert ("step", f"To add them, run this in WSL: {command}") in runner.reporter.messages  # type: ignore[attr-defined]


def test_unattended_refuses_to_install_wsl_by_name() -> None:
    runner = _unattended_runner()
    runner.which = lambda _command: "wsl"  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="wsl --install -d Ubuntu"):
        prerequisites.install_wsl_ubuntu(runner)

    assert runner.commands == []


def test_unattended_windows_host_sets_the_wsl_shell_as_root() -> None:
    runner = _unattended_runner(
        outputs={tuple(wsl_exec_command("Ubuntu", ["id", "-un"])): (0, "dev\n")}
    )

    with (
        mock.patch.object(configs, "is_running_in_wsl", return_value=False),
        mock.patch.object(prerequisites, "is_running_in_wsl", return_value=False),
    ):
        configs.set_wsl_default_shell(runner, _windows_platform())

    assert runner.commands[-1] == wsl_root_exec_command(
        "Ubuntu", ["sh", "-c", "chsh -s /usr/bin/zsh dev"]
    )


def test_unattended_inside_wsl_skips_the_shell_change_when_sudo_needs_a_password() -> None:
    runner = _unattended_runner(
        outputs={
            ("id", "-un"): (0, "dev\n"),
            ("sudo", "-n", "true"): (1, ""),
        }
    )

    with (
        mock.patch.object(configs, "is_running_in_wsl", return_value=True),
        mock.patch.object(prerequisites, "is_running_in_wsl", return_value=True),
    ):
        configs.set_wsl_default_shell(runner, _windows_platform())

    assert not [command for command in runner.commands if "chsh" in " ".join(command)]
    assert any(
        level == "warn" and "Skipping default shell change" in message
        for level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )


@pytest.mark.parametrize("interactive", [True, False])
def test_unattended_runs_children_with_an_empty_stdin(*, interactive: bool) -> None:
    runner = Runner(reporter=CapturingReporter(), unattended=True)

    with mock.patch.object(subprocess, "run") as run:
        runner.run(["claude", "update"], interactive=interactive)

    assert run.call_args.kwargs["stdin"] is subprocess.DEVNULL
