from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


def kit_stamps(files: Sequence[Path]) -> tuple[tuple[int, int] | None, ...]:

    stamps: list[tuple[int, int] | None] = []
    for path in files:
        try:
            held = path.stat()
        except OSError:
            stamps.append(None)
            continue
        stamps.append((held.st_mtime_ns, held.st_size))
    return tuple(stamps)


def probe(files: Sequence[Path]) -> str | None:

    for path in files:
        try:
            compile(path.read_bytes(), str(path), "exec")
        except (OSError, SyntaxError, ValueError) as error:
            return f"{path.parent.name}/{path.name}: {type(error).__name__}: {error}"
    return None


def restart() -> None:
    os.execv(sys.executable, [sys.executable, *sys.orig_argv[1:]])  # nosec B606


class Watcher:
    poll_s = 1.0
    settle_s = 5.0

    def __init__(
        self,
        server: Any,
        kit: Any,
        *,
        check_kit: Callable[[], str | None] | None = None,
        log: Callable[[str], object] = sys.stderr.write,
    ) -> None:
        self.server = server
        self.kit = kit
        self.check_kit = check_kit or (lambda: probe(kit.files))
        self.log = log
        self.due = False
        self.tried = kit.stamps
        self.seen = kit.stamps
        self.since = time.monotonic()
        self.clock = time.monotonic
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> Watcher:
        self.thread.start()
        return self

    def stop(self) -> None:
        self.stopped.set()

    def check(self) -> bool:

        now = kit_stamps(self.kit.files)
        if now != self.seen:
            self.seen, self.since = now, self.clock()
        if now == self.tried or self.clock() - self.since < self.settle_s:
            return False
        self.tried = now
        failure = self.check_kit()
        if failure is not None:
            self.log(
                f"board: the changed kit does not load, so the old kit keeps refusing: {failure}\n"
            )
            return False
        self.log("board: the kit changed and loads, so this server restarts on the new kit\n")
        self.due = True
        self.server.shutdown()
        return True

    def _loop(self) -> None:
        while not self.stopped.wait(self.poll_s):
            if self.check():
                return
