from __future__ import annotations

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
