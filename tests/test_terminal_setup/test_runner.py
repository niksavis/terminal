"""Tests for the command runner."""

from __future__ import annotations

import platform as platform_module
from pathlib import Path

from terminal_setup.runner import ConsoleReporter, Runner


class CapturingReporter:
    """Reporter that records all messages for assertions."""

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


def test_runner_dry_run_does_not_execute(tmp_path: Path) -> None:
    """Dry-run mode must not create files or run real commands."""
    reporter = CapturingReporter()
    runner = Runner(dry_run=True, reporter=reporter)

    target = tmp_path / "nested" / "file.txt"
    runner.write_text(target, "hello")

    assert not target.exists()
    assert ("info", f"write file {target}") in reporter.messages


def test_runner_writes_file(tmp_path: Path) -> None:
    """Non-dry-run write_text creates the file and parent directories."""
    reporter = CapturingReporter()
    runner = Runner(dry_run=False, reporter=reporter)

    target = tmp_path / "nested" / "file.txt"
    runner.write_text(target, "hello")

    assert target.exists()
    assert target.read_text(encoding="utf-8") == "hello"


def test_runner_ensure_dir(tmp_path: Path) -> None:
    """ensure_dir creates directories in non-dry-run mode."""
    runner = Runner(dry_run=False, reporter=ConsoleReporter())
    target = tmp_path / "a" / "b"
    runner.ensure_dir(target)
    assert target.is_dir()


def test_runner_copy(tmp_path: Path) -> None:
    """Copy duplicates a file to a new path."""
    source = tmp_path / "source.txt"
    source.write_text("copy me", encoding="utf-8")
    destination = tmp_path / "dest" / "file.txt"

    runner = Runner(dry_run=False, reporter=ConsoleReporter())
    runner.copy(source, destination)

    assert destination.read_text(encoding="utf-8") == "copy me"


def test_runner_symlink_replaces_existing(tmp_path: Path) -> None:
    """Symlink replaces an existing file or symlink, falling back to copy on Windows."""
    source = tmp_path / "source.txt"
    source.write_text("target", encoding="utf-8")
    destination = tmp_path / "link.txt"
    destination.write_text("old", encoding="utf-8")

    runner = Runner(dry_run=False, reporter=ConsoleReporter())
    runner.symlink(source, destination)

    assert destination.read_text(encoding="utf-8") == "target"
    if platform_module.system() != "Windows":
        assert destination.is_symlink()
