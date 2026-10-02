from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

from terminal_setup import agents
from terminal_setup.agents import (
    AGENTS,
    CLAUDE_INSTALL_PS1,
    ensure_agents,
    parse_agents,
    present_query,
    shell_install_script,
    shell_update_script,
)
from terminal_setup.cli import build_parser
from terminal_setup.platform import (
    OperatingSystem,
    PackageManager,
    PlatformInfo,
    wsl_exec_command,
)

from .test_runner import CapturingReporter
from .test_unattended import RecordingRunner, _windows_platform


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("all", AGENTS),
        ("claude", ("claude",)),
        ("Codex, claude,codex", ("codex", "claude")),
    ],
)
def test_parse_agents(value: str, expected: tuple[str, ...]) -> None:
    assert parse_agents(value) == expected


@pytest.mark.parametrize("value", ["gemini", "claude,cursor", ""])
def test_parse_agents_refuses_an_unknown_name(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="choose from claude, copilot, codex"):
        parse_agents(value)


def test_agents_flag_defaults_to_none() -> None:
    assert build_parser().parse_args([]).agents == ()
    assert build_parser().parse_args(["--agents", "all"]).agents == AGENTS


@pytest.mark.skipif(
    sys.platform == "win32", reason="the query runs in a POSIX sh inside WSL or on a Unix host"
)
@pytest.mark.parametrize(
    ("found", "present"),
    [("/home/dev/.local/bin/codex", 0), ("/mnt/c/Users/dev/nodejs/codex", 1), ("", 1)],
)
def test_present_query_ignores_a_windows_copy_seen_from_wsl(
    tmp_path: Path, found: str, present: int
) -> None:
    script = present_query("codex").replace("command -v codex", f"echo {found}; test -n '{found}'")
    result = subprocess.run(["sh", "-c", script], check=False, cwd=tmp_path)

    assert result.returncode == present


def _wsl(script: str) -> list[str]:
    return wsl_exec_command("Ubuntu", ["sh", "-c", script])


def _linux_platform() -> PlatformInfo:
    return replace(
        _windows_platform(), os=OperatingSystem.LINUX, package_manager=PackageManager.APT
    )


def _run_shell(
    selected: tuple[str, ...], *, update: bool, outputs: dict[tuple[str, ...], tuple[int, str]]
) -> RecordingRunner:
    runner = RecordingRunner(reporter=CapturingReporter(), outputs=outputs)
    with (
        mock.patch.object(agents, "is_running_in_wsl", return_value=True),
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=True),
    ):
        ensure_agents(runner, _linux_platform(), selected, update=update)
    return runner


def _absent(*names: str) -> dict[tuple[str, ...], tuple[int, str]]:
    return {("sh", "-c", present_query(name)): (1, "") for name in names}


def test_shell_installs_only_the_selected_absent_agents() -> None:
    runner = _run_shell(("claude", "codex"), update=False, outputs=_absent(*AGENTS))

    installs = [command[-1] for command in runner.commands if "install" in command[-1]]
    assert installs == [shell_install_script("claude"), shell_install_script("codex")]


def test_shell_skips_a_present_agent() -> None:
    runner = _run_shell(AGENTS, update=False, outputs={})

    assert [command[-1] for command in runner.commands] == [present_query(a) for a in AGENTS]
    assert ("success", "codex is present on this host") in runner.reporter.messages  # type: ignore[attr-defined]


def test_shell_update_runs_the_self_update_of_each_present_agent() -> None:
    runner = _run_shell((), update=True, outputs=_absent("copilot"))

    scripts = [command[-1] for command in runner.commands]
    assert shell_update_script("claude") in scripts
    assert shell_update_script("codex") in scripts
    assert shell_update_script("copilot") not in scripts
    assert shell_install_script("copilot") not in scripts


def test_shell_install_runs_in_wsl_from_a_windows_host(tmp_path: Path) -> None:
    runner = RecordingRunner(
        reporter=CapturingReporter(),
        outputs={tuple(_wsl(present_query("copilot"))): (1, "")},
        has_sudo=False,
    )
    platform = replace(_windows_platform(), home=tmp_path)

    with (
        mock.patch.object(agents, "is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch.object(agents, "_windows_npm", return_value="C:/nodejs/npm.cmd"),
    ):
        ensure_agents(runner, platform, ("copilot",), update=False)

    assert _wsl(shell_install_script("copilot")) in runner.commands
    assert ["C:/nodejs/npm.cmd", "install", "-g", "@github/copilot"] in runner.commands


class WindowsAgentRunner(RecordingRunner):
    found: dict[str, str] = {}  # noqa: RUF012

    def which(self, command: str) -> str | None:
        return self.found.get(command)


def _run_windows(
    tmp_path: Path, selected: tuple[str, ...], found: dict[str, str], *, update: bool = False
) -> WindowsAgentRunner:
    runner = WindowsAgentRunner(reporter=CapturingReporter())
    runner.found = found
    platform = replace(_windows_platform(), home=tmp_path)
    with mock.patch("terminal_setup.prerequisites._add_to_process_path"):
        for agent in AGENTS:
            agents._ensure_windows_agent(
                runner, platform, agent, install=agent in selected, update=update
            )
    return runner


def test_windows_installs_claude_with_its_native_installer(tmp_path: Path) -> None:
    runner = _run_windows(tmp_path, ("claude",), {})

    assert ["powershell", "-NoProfile", "-Command", CLAUDE_INSTALL_PS1] in runner.commands


def test_windows_npm_agent_without_npm_fails_by_name(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="npm is not on the Windows PATH"):
        _run_windows(tmp_path, ("codex",), {})


def test_windows_finds_claude_in_the_local_bin_before_path_refresh(tmp_path: Path) -> None:
    local = tmp_path / ".local" / "bin" / "claude.exe"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"")

    runner = _run_windows(tmp_path, ("claude",), {})

    assert runner.commands == []


def test_windows_update_runs_the_self_update_of_each_user_scope_agent(tmp_path: Path) -> None:
    claude = str(tmp_path / ".local" / "bin" / "claude.exe")
    codex = str(tmp_path / "AppData" / "Roaming" / "npm" / "codex.cmd")
    copilot = "C:/Program Files/GitHub Copilot/copilot.exe"

    runner = _run_windows(
        tmp_path, (), {"claude": claude, "codex": codex, "copilot": copilot}, update=True
    )

    assert runner.commands == [[claude, "update"], [codex, "update"]]
    assert any(
        level == "info" and copilot in message and "managed by your organisation" in message
        for level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )


def test_windows_failed_agent_update_names_the_manual_retry(tmp_path: Path) -> None:
    codex = str(tmp_path / "AppData" / "Local" / "Programs" / "OpenAI" / "Codex" / "codex.exe")
    runner = WindowsAgentRunner(reporter=CapturingReporter())
    runner.found = {"codex": codex}
    failing = subprocess.CalledProcessError(1, [codex, "update"])

    with (
        mock.patch.object(runner, "run", side_effect=failing),
        pytest.raises(subprocess.CalledProcessError),
    ):
        agents._ensure_windows_agent(
            runner, replace(_windows_platform(), home=tmp_path), "codex", install=False, update=True
        )

    assert ("step", "To retry, run 'codex update' in Windows PowerShell (powershell.exe).") in (
        runner.reporter.messages  # type: ignore[attr-defined]
    )
