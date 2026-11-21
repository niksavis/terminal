from __future__ import annotations

import io
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest

from terminal_setup import cli, progress
from terminal_setup.runner import ConsoleReporter, Runner


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _plain(tmp_path: Path, total: int = 2) -> tuple[progress.PhasedReporter, io.StringIO, Clock]:
    stream = io.StringIO()
    clock = Clock()
    reporter = progress.PhasedReporter(
        progress.PlainDisplay(stream), tmp_path / "setup.log", total, clock=clock
    )
    return reporter, stream, clock


def test_plain_mode_prints_one_line_per_phase_and_a_summary(tmp_path: Path) -> None:
    reporter, stream, clock = _plain(tmp_path)

    reporter.header("terminal setup v1.0.0 (Windows host + WSL)")
    reporter.phase("WSL tools", "WSL")
    reporter.info("lazygit is already up to date (installed: 0.66.3, latest: 0.66.3)")
    reporter.info("installed sd 1.1.0 into /home/u/.local/bin/sd")
    reporter.command(["sh", "-c", "true"], "link fd to fdfind")
    clock.now = 14
    reporter.phase("Windows tools", "Windows")
    reporter.info("starship: keeps C:/Program Files/starship/bin/starship.exe (machine-wide)")
    reporter.success("rg 15.2.0 is up to date")
    clock.now = 23
    reporter.step("See which tools need an update anytime with: terminal status")
    reporter.finish()

    assert stream.getvalue().splitlines() == [
        "terminal setup v1.0.0 (Windows host + WSL)",
        f"log: {tmp_path / 'setup.log'}",
        "[1/2] WSL tools...",
        "[1/2] WSL tools: 1 ok, 1 updated (sd 1.1.0) (14 s)",
        "[2/2] Windows tools...",
        "[2/2] Windows tools: 1 ok, 1 managed (starship) (9 s)",
        "summary WSL: updated sd 1.1.0; ok 1; managed -; failed -",
        "summary Windows: updated -; ok 1; managed starship; failed -",
        f"Done in 23 s. Full log: {tmp_path / 'setup.log'}",
        "Next: See which tools need an update anytime with: terminal status",
    ]


def test_warnings_and_errors_print_as_their_own_lines(tmp_path: Path) -> None:
    reporter, stream, _clock = _plain(tmp_path, total=1)

    reporter.phase("Tools", "Linux")
    reporter.warn("Restart the WSL session for the updated PATH to take effect.")
    reporter.error("install fd failed: exit code 1")
    reporter.finish()

    lines = stream.getvalue().splitlines()
    assert "warning: Restart the WSL session for the updated PATH to take effect." in lines
    assert "error: install fd failed: exit code 1" in lines
    assert "[1/1] Tools: 1 warning, 1 failed (0 s)" in lines
    assert "summary Linux: updated -; ok 0; managed -; failed Tools" in lines


def test_the_log_holds_every_detail_and_command_output(tmp_path: Path) -> None:
    reporter, _stream, _clock = _plain(tmp_path, total=1)

    reporter.phase("Configuration", "Linux")
    reporter.info("write file /home/u/.zshrc")
    reporter.output("first line\n\nsecond line\n")
    reporter.finish()

    log = (tmp_path / "setup.log").read_text(encoding="utf-8")
    assert "write file /home/u/.zshrc" in log
    assert "output  first line" in log
    assert "output  second line" in log


@pytest.mark.parametrize(
    ("level", "message", "kind"),
    [
        ("success", "codex 0.171.0 is up to date in WSL", "ok"),
        ("info", "installed sd 1.1.0 into /x/sd", "updated"),
        ("info", "starship: keeps C:/x (machine-wide; removing it needs administrator)", "managed"),
        ("warn", "Restart your terminal", "warning"),
        ("error", "install fd failed", "failed"),
        ("info", "write file /x", "detail"),
        ("success", "Setup complete.", "detail"),
    ],
)
def test_each_message_lands_in_one_count(level: str, message: str, kind: str) -> None:
    assert progress.classify(level, message)[0] == kind


class RecordingDisplay(progress.PlainDisplay):
    def __init__(self) -> None:
        super().__init__(io.StringIO())
        self.events: list[str] = []

    @contextmanager
    def pause(self) -> Iterator[None]:
        self.events.append("pause")
        yield
        self.events.append("resume")


def test_a_question_pauses_the_live_display(tmp_path: Path) -> None:
    display = RecordingDisplay()

    def ask(prompt: str) -> str:
        display.events.append(f"ask {prompt}")
        return "y"

    reporter = progress.PhasedReporter(display, tmp_path / "setup.log", 1, ask=ask)
    reporter.phase("Windows tools", "Windows")

    assert reporter.confirm("Replace the winget copy?") is True
    assert display.events == ["pause", "ask Replace the winget copy? [y/N]: ", "resume"]


def test_an_interactive_command_pauses_the_live_display(tmp_path: Path) -> None:
    display = RecordingDisplay()
    reporter = progress.PhasedReporter(display, tmp_path / "setup.log", 1)
    runner = Runner(reporter=reporter)

    runner.run([sys.executable, "-c", "pass"], interactive=True)

    assert display.events == ["pause", "resume"]


def test_setup_keeps_the_newest_ten_logs(tmp_path: Path) -> None:
    for day in range(1, 13):
        (tmp_path / f"setup-202611{day:02d}-000000.log").write_text("", encoding="utf-8")

    path = progress.new_log(tmp_path, datetime(2026, 11, 21, 17, 5, 0))

    kept = sorted(item.name for item in tmp_path.glob("setup-*.log"))
    assert len(kept) == 9
    assert kept[0] == "setup-20261104-000000.log"
    assert path.name == "setup-20261121-170500.log"


def test_setup_prints_plain_lines_when_stdout_is_not_a_terminal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(progress, "use_rich", lambda: False)

    chosen = cli._setup_reporter(cli.build_parser().parse_args([]))

    assert isinstance(chosen, progress.PhasedReporter)
    assert chosen.log_path.parent == tmp_path / "terminal-setup" / "logs"


@pytest.mark.parametrize("arguments", [["--verbose"], ["--only", "status"], ["--only", "check"]])
def test_verbose_and_read_only_modes_keep_the_full_output(arguments: list[str]) -> None:
    assert isinstance(
        cli._setup_reporter(cli.build_parser().parse_args(arguments)), ConsoleReporter
    )


def test_rich_is_used_only_for_a_terminal_without_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert progress.use_rich(Tty()) is True
    assert progress.use_rich(io.StringIO()) is False
    monkeypatch.setenv("NO_COLOR", "1")
    assert progress.use_rich(Tty()) is False
