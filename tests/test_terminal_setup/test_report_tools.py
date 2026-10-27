from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from unittest import mock

from terminal_setup import cli
from terminal_setup.agents import present_query
from terminal_setup.platform import setup_command, wsl_exec_command

from .test_runner import CapturingReporter
from .test_unattended import RecordingRunner, _windows_platform

HOME = Path("C:/Users/Dev")
PATHS = {
    "uv": "C:/Users/Dev/.local/bin/uv.exe",
    "python": "C:/Program Files/Python314/python.exe",
    "claude": "C:/Users/Dev/.local/bin/claude.exe",
}


class WhichRunner(RecordingRunner):
    found: dict[str, str] = {}  # noqa: RUF012

    def which(self, command: str) -> str | None:
        return self.found.get(command)


def _windows_report() -> list[tuple[str, str]]:
    runner = WhichRunner(
        reporter=CapturingReporter(),
        outputs={
            (PATHS["uv"], "--version"): (0, "uv 0.12.22\n"),
            (PATHS["python"], "--version"): (0, "Python 3.14.7\n"),
            (PATHS["claude"], "--version"): (0, "2.1.287 (Claude Code)\n"),
        },
    )
    runner.found = PATHS
    with mock.patch.object(cli.prerequisites, "windows_tool_candidate_dirs", return_value=[]):
        cli._print_windows_report(
            runner, replace(_windows_platform(), home=HOME), include_starship=False
        )
    return runner.reporter.messages  # type: ignore[attr-defined]


def test_windows_report_lists_runtimes_with_version_and_scope() -> None:
    messages = _windows_report()

    assert ("success", f"windows:uv ({PATHS['uv']}, uv 0.12.22, user profile)") in messages
    assert (
        "success",
        f"windows:python ({PATHS['python']}, Python 3.14.7, machine-wide)",
    ) in messages


def test_windows_report_warns_for_a_missing_runtime() -> None:
    assert ("warn", "windows:node (not found)") in _windows_report()


def test_windows_report_shows_a_missing_agent_as_optional() -> None:
    messages = _windows_report()

    assert (
        "success",
        f"windows:claude ({PATHS['claude']}, 2.1.287 (Claude Code), user profile)",
    ) in (messages)
    assert (
        "info",
        "windows:codex: not installed (optional; to install it, run: "
        f"{setup_command('--agents codex')})",
    ) in messages
    assert not [message for level, message in messages if level == "warn" and "codex" in message]


def test_wsl_report_lists_the_agents_and_ignores_windows_copies() -> None:
    script = present_query("codex") + '; echo "$found"'
    runner = RecordingRunner(
        reporter=CapturingReporter(),
        outputs={
            tuple(wsl_exec_command("Ubuntu", ["sh", "-c", script])): (
                0,
                "/home/dev/.local/bin/codex\n",
            ),
        },
    )

    with mock.patch.object(cli, "is_running_in_wsl", return_value=False):
        found = cli._shell_agent_path(runner, "codex", wsl_distro="Ubuntu")
        absent = cli._shell_agent_path(runner, "claude", wsl_distro="Ubuntu")

    assert found == "/home/dev/.local/bin/codex"
    assert absent is None


def test_windows_report_warns_for_a_runtime_below_its_target() -> None:
    runner = WhichRunner(
        reporter=CapturingReporter(),
        outputs={
            (PATHS["python"], "--version"): (0, "Python 3.13.2\n"),
            ("C:/Program Files/nodejs/node.exe", "--version"): (0, "v24.11.0\n"),
        },
    )
    runner.found = {"python": PATHS["python"], "node": "C:/Program Files/nodejs/node.exe"}
    with mock.patch.object(cli.prerequisites, "windows_tool_candidate_dirs", return_value=[]):
        cli._print_windows_report(
            runner, replace(_windows_platform(), home=HOME), include_starship=False
        )
    messages = runner.reporter.messages  # type: ignore[attr-defined]

    assert (
        "warn",
        f"windows:python ({PATHS['python']}, Python 3.13.2, machine-wide, below the target 3.14)",
    ) in messages
    assert (
        "warn",
        "windows:node (C:/Program Files/nodejs/node.exe, v24.11.0, machine-wide, "
        "below the target v26)",
    ) in messages


class WslScriptRunner(RecordingRunner):
    replies: dict[str, str] = {}  # noqa: RUF012

    def run(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        for needle, stdout in self.replies.items():
            if needle in command[-1]:
                return subprocess.CompletedProcess(command, 0, stdout, "")
        return subprocess.CompletedProcess(command, 0, "", "")


def _wsl_report(replies: dict[str, str]) -> list[tuple[str, str]]:
    runner = WslScriptRunner(reporter=CapturingReporter())
    runner.replies = replies
    with mock.patch.object(cli, "is_running_in_wsl", return_value=True):
        cli._print_wsl_report(runner, _windows_platform(), include_starship=False)
    return runner.reporter.messages  # type: ignore[attr-defined]


def test_wsl_report_shows_the_version_of_each_tool() -> None:
    messages = _wsl_report({
        "command -v fd ": "/home/dev/.local/bin/fd\nfd 10.5.0\n",
        "command -v python3 ": "/home/dev/.local/bin/python3\nPython 3.14.10\n",
        "command -v node ": "/home/dev/.local/bin/node\nv26.12.1\n",
    })

    assert ("success", "wsl:fd (/home/dev/.local/bin/fd, fd 10.5.0)") in messages
    assert ("success", "wsl:python3 (/home/dev/.local/bin/python3, Python 3.14.10)") in messages
    assert ("success", "wsl:node (/home/dev/.local/bin/node, v26.12.1)") in messages


def test_wsl_report_warns_for_a_runtime_below_its_target() -> None:
    messages = _wsl_report({
        "command -v python3 ": "/usr/bin/python3\nPython 3.12.3\n",
        "command -v node ": "/usr/bin/node\nv24.11.0\n",
    })

    assert ("warn", "wsl:python3 (/usr/bin/python3, Python 3.12.3, below the target 3.14)") in (
        messages
    )
    assert ("warn", "wsl:node (/usr/bin/node, v24.11.0, below the target v26)") in messages


def test_wsl_report_asks_tmux_for_its_version_with_its_own_flag() -> None:
    runner = WslScriptRunner(reporter=CapturingReporter())
    with mock.patch.object(cli, "is_running_in_wsl", return_value=True):
        cli._print_wsl_report(runner, _windows_platform(), include_starship=False)

    scripts = [command[-1] for command in runner.commands]
    assert any("command -v tmux " in s and '"$p" -V ' in s for s in scripts)
    assert not any("command -v img-zoom " in s and "--version" in s for s in scripts)


HERDR_STATUS = (
    "pi: not installed (/home/dev/.pi/agent/extensions/herdr-agent-state.ts)\n"
    "claude: current (v11) (/home/dev/.claude/hooks/herdr-agent-state.sh)\n"
    "codex: outdated (v9) (/home/dev/.codex/herdr-agent-state.sh)\n"
    "copilot: not installed (/home/dev/.copilot/hooks/herdr-agent-state.sh)\n"
)


def _herdr_argv(*arguments: str) -> list[str]:
    run = 'PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"; exec herdr "$@"'
    return wsl_exec_command("Ubuntu", ["sh", "-c", run, "herdr", *arguments])


def test_setup_installs_a_herdr_integration_only_for_each_named_agent() -> None:
    runner = RecordingRunner(reporter=CapturingReporter())

    with mock.patch.object(cli.agents, "is_running_in_wsl", return_value=False):
        cli.agents.ensure_herdr_integrations(runner, _windows_platform(), ("codex", "claude"))

    assert runner.commands == [
        _herdr_argv("integration", "install", "claude"),
        _herdr_argv("integration", "install", "codex"),
    ]


def test_the_report_shows_each_herdr_integration_state() -> None:
    runner = RecordingRunner(
        reporter=CapturingReporter(),
        outputs={tuple(_herdr_argv("integration", "status")): (0, HERDR_STATUS)},
    )

    with mock.patch.object(cli.agents, "is_running_in_wsl", return_value=False):
        cli._report_herdr_integrations(runner, _windows_platform(), "wsl")
    messages = runner.reporter.messages  # type: ignore[attr-defined]

    assert ("success", "wsl:herdr-claude (current (v11))") in messages
    assert (
        "warn",
        "wsl:herdr-codex (outdated (v9); to update it, run: "
        f"{setup_command('--update --herdr --agents codex')})",
    ) in messages
    assert (
        "info",
        "wsl:herdr-copilot: not installed (optional; to install it, run: "
        f"{setup_command('--herdr --agents copilot')})",
    ) in messages
    assert not [message for _, message in messages if "herdr-pi" in message]
