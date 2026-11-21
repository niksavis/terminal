from __future__ import annotations

import os
import re
import shlex
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TextIO

if TYPE_CHECKING:
    from rich.spinner import Spinner

LOG_KEEP = 10
_UPDATED = re.compile(
    r"^(?:installed|updated|upgraded) (?P<name>[\w.+-]+)(?: (?P<version>v?\d[\w.+-]*))?"
)
_MANAGED = ("machine-wide", "keeps ")
_FINAL_FAILURES = "Setup finished with "
_CURRENT = (" is up to date", " is already up to date", " is present")


def log_dir(*, windows_host: bool, home: Path) -> Path:
    if windows_host:
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else home / "AppData" / "Local"
    else:
        state = os.environ.get("XDG_STATE_HOME")
        base = Path(state) if state else home / ".local" / "state"
    return base / "terminal-setup" / "logs"


def new_log(directory: Path, now: datetime) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    old = sorted(directory.glob("setup-*.log"))
    for stale in old[: max(0, len(old) - (LOG_KEEP - 1))]:
        stale.unlink(missing_ok=True)
    return directory / f"setup-{now:%Y%m%d-%H%M%S}.log"


@dataclass
class Phase:
    name: str
    side: str
    started: float
    ok: int = 0
    updated: list[str] = field(default_factory=list)
    managed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    seconds: int = 0

    def summary(self) -> str:
        parts = []
        if self.ok:
            parts.append(f"{self.ok} ok")
        if self.updated:
            parts.append(f"{len(self.updated)} updated ({', '.join(self.updated)})")
        if self.managed:
            parts.append(f"{len(self.managed)} managed ({', '.join(self.managed)})")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning{'s' if len(self.warnings) > 1 else ''}")
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        return ", ".join(parts) or "nothing to do"

    @property
    def mark(self) -> str:
        if self.failed:
            return "x"
        return "!" if self.warnings else "ok"


def _is_ok(level: str, message: str) -> bool:
    if level == "success":
        return message != "Setup complete."
    return level == "info" and any(word in message for word in _CURRENT)


def _updated_name(found: re.Match[str]) -> str:
    version = found.group("version")
    return f"{found.group('name')} {version}" if version else found.group("name")


def classify(level: str, message: str) -> tuple[str, str]:
    if level == "error" and (message.startswith(_FINAL_FAILURES) or message.startswith("  - ")):
        return "notice", message
    if level == "error" or (level == "warn" and message.endswith(" (continuing)")):
        return "failed", message
    if any(word in message for word in _MANAGED):
        return "managed", message.split(":", 1)[0].strip()
    if level == "warn":
        return "warning", message
    found = _UPDATED.match(message) if level in {"info", "success"} else None
    if found:
        return "updated", _updated_name(found)
    return ("ok" if _is_ok(level, message) else "detail"), message


class Display(Protocol):
    def header(self, title: str, log: Path, /) -> None: ...

    def start(self, index: int, total: int, name: str, /) -> None: ...

    def progress(self, text: str, /) -> None: ...

    def line(self, kind: str, text: str, /) -> None: ...

    def end(self, index: int, total: int, phase: Phase, /) -> None: ...

    def text(self, line: str, /) -> None: ...

    def summary(self, sides: dict[str, dict[str, str]], /) -> None: ...

    def pause(self) -> AbstractContextManager[None]: ...


class PlainDisplay:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout

    def _write(self, line: str) -> None:
        self._stream.write(line + "\n")
        self._stream.flush()

    def header(self, title: str, log: Path) -> None:
        self._write(title)
        self._write(f"log: {log}")

    def start(self, index: int, total: int, name: str) -> None:
        self._write(f"[{index}/{total}] {name}...")

    def progress(self, _text: str) -> None:
        return

    def line(self, kind: str, text: str) -> None:
        self._write(f"{kind}: {text}")

    def end(self, index: int, total: int, phase: Phase) -> None:
        self._write(f"[{index}/{total}] {phase.name}: {phase.summary()} ({phase.seconds} s)")

    def text(self, line: str) -> None:
        self._write(line)

    def summary(self, sides: dict[str, dict[str, str]]) -> None:
        for name, side in sides.items():
            self._write(
                f"summary {name}: updated {side['updated']}; ok {side['ok']}; "
                f"managed {side['managed']}; failed {side['failed']}"
            )

    @contextmanager
    def pause(self) -> Iterator[None]:
        yield


class RichDisplay:
    def __init__(self) -> None:
        from rich.console import Console  # noqa: PLC0415

        self._console = Console(highlight=False)
        self._live = None
        self._name = ""

    def header(self, title: str, log: Path) -> None:
        self._console.print(title, style="bold", markup=False)
        self._console.print(f"log: {log}", style="dim", markup=False, soft_wrap=True)

    def _spinner(self, text: str) -> Spinner:
        from rich.spinner import Spinner  # noqa: PLC0415
        from rich.text import Text  # noqa: PLC0415

        return Spinner("dots", text=Text(text))

    def start(self, index: int, total: int, name: str) -> None:
        from rich.live import Live  # noqa: PLC0415

        self._name = name
        self._live = Live(
            self._spinner(f"{name}  ({index}/{total})"),
            console=self._console,
            transient=True,
            refresh_per_second=8,
        )
        self._live.start()

    def progress(self, text: str) -> None:
        if self._live is not None:
            self._live.update(self._spinner(f"{self._name}  {text}"))

    def line(self, kind: str, text: str) -> None:
        style = {"error": "red", "warning": "yellow", "question": "magenta"}.get(kind, "")
        marker = "?" if kind == "question" else "!"
        self._console.print(f"    {marker} {text}", style=style, markup=False)

    def end(self, _index: int, _total: int, phase: Phase) -> None:
        self._stop()
        mark, style = {"ok": ("✓", "green"), "!": ("!", "yellow"), "x": ("✗", "red")}[phase.mark]
        self._console.print(f"{mark} ", style=style, end="", markup=False)
        line = f"{phase.name:<20} {phase.summary():<84} {phase.seconds:>3} s"
        self._console.print(line, markup=False)

    def text(self, line: str) -> None:
        self._console.print(line, markup=False, soft_wrap=True)

    def summary(self, sides: dict[str, dict[str, str]]) -> None:
        from rich.table import Table  # noqa: PLC0415

        table = Table(box=None, show_header=True, pad_edge=False)
        table.add_column("")
        for name in sides:
            table.add_column(name)
        for row in ("updated", "ok", "managed", "failed"):
            table.add_row(row, *(side[row] for side in sides.values()))
        self._console.print()
        self._console.print(table)
        self._console.print()

    def _stop(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    @contextmanager
    def pause(self) -> Iterator[None]:
        live = self._live
        if live is None:
            yield
            return
        live.stop()
        try:
            yield
        finally:
            live.start()


def use_rich(stream: TextIO | None = None) -> bool:
    stream = stream or sys.stdout
    return (
        stream is not None
        and stream.isatty()
        and os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM") != "dumb"
    )


class PhasedReporter:
    def __init__(
        self,
        display: Display,
        log: Path,
        total: int,
        clock: Callable[[], float] = time.monotonic,
        ask: Callable[[str], str] = input,
    ) -> None:
        self._display = display
        self._log_path = log
        self._log = log.open("a", encoding="utf-8")
        self._total = total
        self._clock = clock
        self._ask = ask
        self._started = clock()
        self._phases: list[Phase] = []
        self._current: Phase | None = None
        self.hints: list[str] = []

    @property
    def log_path(self) -> Path:
        return self._log_path

    def header(self, title: str) -> None:
        self._display.header(title, self._log_path)
        self._write("title", title)

    def _write(self, level: str, message: str) -> None:
        self._log.write(f"{datetime.now():%H:%M:%S} {level:<7} {message}\n")
        self._log.flush()

    def phase(self, name: str, side: str) -> None:
        self._close_phase()
        self._current = Phase(name, side, self._clock())
        self._phases.append(self._current)
        self._write("phase", name)
        self._display.start(len(self._phases), self._total, name)

    def _close_phase(self) -> None:
        if self._current is None:
            return
        self._current.seconds = round(self._clock() - self._current.started)
        self._display.end(len(self._phases), self._total, self._current)
        self._current = None

    def _record(self, level: str, message: str) -> None:
        self._write(level, message)
        kind, item = classify(level, message)
        phase = self._current
        if kind == "notice":
            self._display.line("error", message)
        elif kind == "failed":
            if phase is not None:
                phase.failed.append(item)
            self._display.line("error", message)
        elif kind == "warning":
            if phase is not None:
                phase.warnings.append(item)
            self._display.line("warning", message)
        elif phase is not None and kind == "managed":
            if item not in phase.managed:
                phase.managed.append(item)
        elif phase is not None and kind == "updated":
            phase.updated.append(item)
        elif phase is not None and kind == "ok":
            phase.ok += 1
        else:
            self._display.progress(message[:80])

    def info(self, message: str) -> None:
        self._record("info", message)

    def success(self, message: str) -> None:
        self._record("success", message)

    def warn(self, message: str) -> None:
        self._record("warn", message)

    def error(self, message: str) -> None:
        self._record("error", message)

    def step(self, message: str) -> None:
        self._write("step", message)
        self.hints.append(message)

    def plan(self, total: int) -> None:
        self._total = total

    def prompt(self, message: str) -> None:
        self._write("prompt", message)
        with self._display.pause():
            self._display.line("question", message)

    def command(self, command: list[str], label: str | None = None) -> None:
        self._write("run", f"{label}: {shlex.join(command)}" if label else shlex.join(command))
        self._display.progress(label or shlex.join(command)[:80])

    def output(self, text: str) -> None:
        for line in text.splitlines():
            if line.strip():
                self._write("output", line)

    def confirm(self, message: str) -> bool:
        self._write("prompt", message)
        with self._display.pause():
            try:
                answer = self._ask(f"{message} [y/N]: ")
            except EOFError, OSError:
                answer = ""
        self._write("answer", answer)
        return answer.strip().lower() in {"y", "yes"}

    @contextmanager
    def paused(self) -> Iterator[None]:
        with self._display.pause():
            yield

    def finish(self) -> None:
        self._close_phase()
        sides: dict[str, dict[str, str]] = {}
        for phase in self._phases:
            side = sides.setdefault(
                phase.side, {"updated": "", "ok": "0", "managed": "", "failed": ""}
            )
            side["updated"] = ", ".join(filter(None, [side["updated"], *phase.updated]))
            side["managed"] = ", ".join(filter(None, [side["managed"], *phase.managed]))
            side["failed"] = ", ".join(
                filter(None, [side["failed"], phase.name if phase.failed else ""])
            )
            side["ok"] = str(int(side["ok"]) + phase.ok)
        self._display.summary({
            name: {key: value or "-" for key, value in side.items()} for name, side in sides.items()
        })
        seconds = round(self._clock() - self._started)
        self._display.text(f"Done in {seconds} s. Full log: {self._log_path}")
        for hint in self.hints:
            self._display.text(f"Next: {hint}")
        self._log.close()


def paused(reporter: object) -> AbstractContextManager[None]:
    if isinstance(reporter, PhasedReporter):
        return reporter.paused()
    return nullcontext()


def log_output(reporter: object, text: str) -> None:
    if isinstance(reporter, PhasedReporter) and text:
        reporter.output(text)
