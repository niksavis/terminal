"""Command execution wrapper with dry-run support."""

from __future__ import annotations

import shutil
import subprocess  # nosec B404
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

    def command(self, command: list[str]) -> None:
        """Report a command that is about to run."""
        ...

    def confirm(self, message: str) -> bool:
        """Ask the user a yes/no question and return the answer."""
        ...


class ConsoleReporter:
    """Default reporter that prints to stdout/stderr."""

    def info(self, message: str) -> None:
        """Print an informational message."""
        print(f"INFO: {message}")

    def warn(self, message: str) -> None:
        """Print a warning message."""
        print(f"WARN: {message}")

    def error(self, message: str) -> None:
        """Print an error message."""
        print(f"ERROR: {message}")

    def command(self, command: list[str]) -> None:
        """Print a command that is about to run."""
        print(f"RUN: {' '.join(command)}")

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
