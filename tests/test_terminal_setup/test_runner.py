from __future__ import annotations

import platform as platform_module
from pathlib import Path

import pytest

from terminal_setup.runner import ConsoleReporter, Runner


class CapturingReporter:
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


def test_runner_dry_run_does_not_execute(tmp_path: Path) -> None:
    reporter = CapturingReporter()
    runner = Runner(dry_run=True, reporter=reporter)

    target = tmp_path / "nested" / "file.txt"
    runner.write_text(target, "hello")

    assert not target.exists()
    assert ("info", f"write file {target}") in reporter.messages


def test_runner_writes_file(tmp_path: Path) -> None:
    reporter = CapturingReporter()
    runner = Runner(dry_run=False, reporter=reporter)

    target = tmp_path / "nested" / "file.txt"
    runner.write_text(target, "hello")

    assert target.exists()
    assert target.read_text(encoding="utf-8") == "hello"


def test_runner_ensure_dir(tmp_path: Path) -> None:
    runner = Runner(dry_run=False, reporter=ConsoleReporter())
    target = tmp_path / "a" / "b"
    runner.ensure_dir(target)
    assert target.is_dir()


def test_runner_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("copy me", encoding="utf-8")
    destination = tmp_path / "dest" / "file.txt"

    runner = Runner(dry_run=False, reporter=ConsoleReporter())
    runner.copy(source, destination)

    assert destination.read_text(encoding="utf-8") == "copy me"


def test_runner_symlink_replaces_existing(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("target", encoding="utf-8")
    destination = tmp_path / "link.txt"
    destination.write_text("old", encoding="utf-8")

    runner = Runner(dry_run=False, reporter=ConsoleReporter())
    runner.symlink(source, destination)

    assert destination.read_text(encoding="utf-8") == "target"
    if platform_module.system() != "Windows":
        assert destination.is_symlink()


def test_runner_write_text_forces_lf_newlines(tmp_path: Path) -> None:
    destination = tmp_path / "script.sh"

    runner = Runner(dry_run=False, reporter=ConsoleReporter())
    runner.write_text(destination, "#!/bin/bash\necho ok\n")

    assert b"\r" not in destination.read_bytes()


def test_runner_copy_forces_lf_newlines(tmp_path: Path) -> None:
    source = tmp_path / "source.sh"
    source.write_text("#!/bin/bash\necho ok\n", encoding="utf-8", newline="\n")
    destination = tmp_path / "dest.sh"

    runner = Runner(dry_run=False, reporter=ConsoleReporter())
    runner.copy(source, destination)

    assert b"\r" not in destination.read_bytes()


def test_console_reporter_prints_the_label_in_place_of_the_script(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ConsoleReporter().command(
        ["wsl", "-d", "Ubuntu", "--exec", "sh", "-c", "echo hidden"], "say hi"
    )

    out = capsys.readouterr().out
    assert "wsl -d Ubuntu --exec sh: say hi" in out
    assert "hidden" not in out


def test_console_reporter_prints_an_unlabelled_command_in_full(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ConsoleReporter().command(["sh", "-c", "echo shown"])

    assert "sh -c 'echo shown'" in capsys.readouterr().out


def test_console_reporter_cuts_a_powershell_script_at_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ConsoleReporter().command(["pwsh", "-NoProfile", "-Command", "Write-Host hidden"], "greet")

    out = capsys.readouterr().out
    assert "pwsh -NoProfile: greet" in out
    assert "hidden" not in out
