"""Command execution wrapper with dry-run support."""

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
    """Protocol for reporting setup progress."""

    def info(self, message: str) -> None:
        """Report an informational message."""
        ...

    def warn(self, message: str) -> None:
        """Report a warning message."""
        ...

    def error(self, message: str) -> None:
        """Report an error message."""
        ...

    def success(self, message: str) -> None:
        """Report a step that completed successfully."""
        ...

    def step(self, message: str) -> None:
        """Report a phase heading or a next action for the user."""
        ...

    def command(self, command: list[str]) -> None:
        """Report a command that is about to run."""
        ...

    def confirm(self, message: str) -> bool:
        """Ask the user a yes/no question and return the answer."""
        ...


_LEVEL_STYLES = {
    # level: (unicode marker, ANSI colour code, ASCII fallback label)
    "success": ("✓", "32", "[ ok ]"),  # green check
    "error": ("✗", "31", "[fail]"),  # red cross
    "warn": ("⚠", "33", "[warn]"),  # yellow warning sign
    "info": ("•", "2", "[info]"),  # dim bullet
    "step": ("→", "36;1", "[next]"),  # bold cyan arrow
    "run": ("$", "2", "[ run]"),  # dim shell prompt
}


def _stream_supports_color() -> bool:
    """Return True when ANSI colour should be emitted to stdout."""
    return (
        sys.stdout.isatty()
        and os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM") != "dumb"
    )


def _stream_supports_unicode() -> bool:
    """Return True when stdout can encode the marker glyphs."""
    return "utf" in (sys.stdout.encoding or "").lower()


class ConsoleReporter:
    """Default reporter that prints symbol-prefixed, colour-aware progress lines.

    Colour is used only on an interactive terminal (and never when ``NO_COLOR`` is
    set); unicode markers fall back to ASCII labels on non-UTF-8 streams, so output
    stays readable when piped, logged, or run in a legacy console.
    """

    def __init__(self) -> None:
        """Detect colour and unicode support once for this stream."""
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
        """Print an informational message."""
        self._emit("info", message)

    def warn(self, message: str) -> None:
        """Print a warning message."""
        self._emit("warn", message)

    def error(self, message: str) -> None:
        """Print an error message."""
        self._emit("error", message)

    def success(self, message: str) -> None:
        """Print a completed-step message."""
        self._emit("success", message)

    def step(self, message: str) -> None:
        """Print a phase heading or a next action for the user."""
        self._emit("step", message)

    def command(self, command: list[str]) -> None:
        """Print a command that is about to run (truncated to one line on a terminal)."""
        line = shlex.join(command)
        if self._color:
            limit = max(20, shutil.get_terminal_size((100, 24)).columns - 3)
            if len(line) > limit:
                line = line[: limit - 1] + "…"
        self._emit("run", line)

    def confirm(self, message: str) -> bool:
        """Prompt the user for a yes/no answer."""
        try:
            answer = input(f"{message} [y/N]: ")
        except EOFError, OSError:
            return False
        return answer.strip().lower() in {"y", "yes"}


@dataclass
class Runner:
    """Executes commands and filesystem operations, optionally in dry-run mode."""

    dry_run: bool = False
    reporter: Reporter = field(default_factory=ConsoleReporter)

    def run(  # noqa: PLR0913
        self,
        command: list[str],
        *,
        check: bool = True,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        interactive: bool = False,
        dry_run_safe: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command or simulate it when in dry-run mode.

        Set ``interactive=True`` for commands that may prompt for input
        (e.g. ``sudo`` or ``chsh`` asking for a password). In interactive
        mode the terminal's stdin/stdout/stderr are connected directly to
        the child process so the user can respond to prompts.

        Set ``dry_run_safe=True`` for read-only commands (such as
        prerequisite checks) that should always execute so dry-run output
        reflects the real system state.
        """
        # Echo actions, not read-only probes: dry_run_safe commands are inspections
        # (command -v, apt-cache show, version checks) and would only add noise.
        if not dry_run_safe:
            self.reporter.command(command)
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
        """Return the path to a command, or None if missing."""
        return shutil.which(command)

    def ensure_dir(self, path: Path) -> None:
        """Create a directory if it does not exist."""
        self.reporter.info(f"ensure directory {path}")
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)

    def write_text(self, path: Path, content: str) -> None:
        """Write text to a file, creating parent directories as needed."""
        self.reporter.info(f"write file {path}")
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def copy(self, source: Path, destination: Path) -> None:
        """Copy a file, creating parent directories as needed."""
        self.reporter.info(f"copy {source} -> {destination}")
        if not self.dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def confirm(self, prompt: str) -> bool:
        """Ask the user a yes/no question via the reporter."""
        return self.reporter.confirm(prompt)

    def symlink(self, source: Path, destination: Path) -> None:
        """Create a symlink, replacing an existing file if necessary.

        On Windows without developer mode or admin rights, symlinks may fail;
        in that case fall back to copying the file so the setup still works.
        """
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
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
