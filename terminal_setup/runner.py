from __future__ import annotations

import os
import shlex
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class Reporter(Protocol):
    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def success(self, message: str) -> None: ...

    def step(self, message: str) -> None: ...

    def prompt(self, message: str) -> None: ...

    def command(self, command: list[str], label: str | None = None) -> None: ...

    def confirm(self, message: str) -> bool: ...


_LEVEL_STYLES = {
    "success": ("✓", "32", "[ ok ]"),
    "error": ("✗", "31", "[fail]"),
    "warn": ("⚠", "33", "[warn]"),
    "info": ("•", "2", "[info]"),
    "step": ("→", "36;1", "[next]"),
    "prompt": ("?", "35", "[ask ]"),
    "run": ("$", "2", "[ run]"),
}


def _stream_supports_color() -> bool:
    return (
        sys.stdout.isatty()
        and os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM") != "dumb"
    )


def _stream_supports_unicode() -> bool:
    return "utf" in (sys.stdout.encoding or "").lower()


class ConsoleReporter:
    def __init__(self) -> None:
        self._color = _stream_supports_color()
        self._unicode = _stream_supports_unicode()

    def _emit(self, level: str, message: str) -> None:
        marker, color, label = _LEVEL_STYLES[level]
        marker = marker if self._unicode else label
        if self._color:
            print(f"\033[{color}m{marker}\033[0m {message}")
        else:
            print(f"{marker} {message}")

    def info(self, message: str) -> None:
        self._emit("info", message)

    def warn(self, message: str) -> None:
        self._emit("warn", message)

    def error(self, message: str) -> None:
        self._emit("error", message)

    def success(self, message: str) -> None:
        self._emit("success", message)

    def step(self, message: str) -> None:
        self._emit("step", message)

    def prompt(self, message: str) -> None:
        self._emit("prompt", message)

    def command(self, command: list[str], label: str | None = None) -> None:
        line = f"{shlex.join(_before_script(command))}: {label}" if label else shlex.join(command)
        if self._color:
            limit = max(20, shutil.get_terminal_size((100, 24)).columns - 3)
            if len(line) > limit:
                line = line[: limit - 1] + "…"
        self._emit("run", line)

    def confirm(self, message: str) -> bool:
        try:
            answer = input(f"{message} [y/N]: ")
        except EOFError, OSError:
            return False
        return answer.strip().lower() in {"y", "yes"}


_SCRIPT_FLAGS = ("-c", "-Command")


def _before_script(command: list[str]) -> list[str]:
    for index, part in enumerate(command):
        if part in _SCRIPT_FLAGS:
            return command[:index]
    return command


@dataclass
class Runner:
    dry_run: bool = False
    reporter: Reporter = field(default_factory=ConsoleReporter)
    failures: list[str] = field(default_factory=list)
    """Steps that failed but were not allowed to abort the run. See ``attempt``."""

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

        if not dry_run_safe:
            self.reporter.command(command, label)
        if self.dry_run and not dry_run_safe:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="",
                stderr="",
            )
        if interactive:
            return subprocess.run(  # nosec B603
                command,
                check=check,
                cwd=cwd,
                env=env,
                stdin=None,
                stdout=None,
                stderr=None,
                text=True,
            )
        return subprocess.run(  # nosec B603
            command,
            check=check,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
        )

    def which(self, command: str) -> str | None:
        return shutil.which(command)

    def ensure_dir(self, path: Path) -> None:
        self.reporter.info(f"ensure directory {path}")
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)

    def write_text(self, path: Path, content: str) -> None:

        self.reporter.info(f"write file {path}")
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")

    def copy(self, source: Path, destination: Path) -> None:

        self.reporter.info(f"copy {source} -> {destination}")
        if not self.dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
            )

    def confirm(self, prompt: str) -> bool:
        return self.reporter.confirm(prompt)

    def symlink(self, source: Path, destination: Path) -> None:

        self.reporter.info(f"symlink {source} -> {destination}")
        if self.dry_run:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            destination.unlink()
        try:
            destination.symlink_to(source)
        except OSError:
            self.reporter.warn(f"symlink failed for {destination}; copying instead")
            destination.write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
            )
