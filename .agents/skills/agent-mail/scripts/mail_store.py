from __future__ import annotations

import os
import re
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

PROG = "agent_mail.py"
NAME = re.compile(r"[a-z][a-z0-9-]{1,30}")


class RefusedError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp() -> str:
    seconds, nanos = divmod(time.time_ns(), 1_000_000_000)
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y%m%dT%H%M%S") + f".{nanos:09d}Z"


def need_name(value: str, kind: str = "name") -> str:
    if not NAME.fullmatch(value):
        raise RefusedError(
            f"bad {kind} {value!r}: use lower-case letters, digits and '-', "
            "2 to 31 characters, a letter first"
        )
    return value


class Mail:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.boxes = root / "mail"
        self.locks = root / "locks"

    def members(self) -> list[str]:
        if not self.boxes.is_dir():
            return []
        return sorted(
            entry.name
            for entry in self.boxes.iterdir()
            if NAME.fullmatch(entry.name) and (entry / "new").is_dir()
        )

    def need_member(self, name: str) -> str:
        need_name(name)
        if not (self.boxes / name / "new").is_dir():
            known = " ".join(self.members()) or "none"
            raise RefusedError(
                f"no agent named {name!r}. Known agents: {known}. "
                f"Take a name with: {PROG} join <prefix>"
            )
        return name

    def touch_seen(self, name: str) -> None:
        part = self.boxes / name / f"seen.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        try:
            part.write_text(now_iso() + "\n", encoding="utf-8")
            part.replace(self.boxes / name / "seen")
        except OSError:
            part.unlink(missing_ok=True)

    def list_new(self, name: str) -> list[str]:
        folder = self.boxes / name / "new"
        return sorted(entry.name for entry in folder.iterdir() if entry.name.endswith(".md"))

    def make_box(self, name: str) -> None:
        for part in ("tmp", "new", "cur"):
            (self.boxes / name / part).mkdir()
        self.touch_seen(name)

    def need_boxes(self) -> None:
        if not self.boxes.is_dir():
            raise RefusedError(f"{self.boxes} is missing. Run: {PROG} init {self.root.parent}")


def subject_of(path: Path) -> str:
    return header(path, "Subject")


def header(path: Path, key: str) -> str:
    prefix = f"{key}: "
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line:
                break
            if line.startswith(prefix):
                return line[len(prefix) :]
    return ""


def place(source: Path, target: Path) -> None:
    try:
        os.link(source, target)
    except FileExistsError:
        raise
    except OSError:
        place_without_link(source, target)
        return
    source.unlink()


def place_without_link(source: Path, target: Path) -> None:
    reserve = target.parent.parent / "tmp" / f"{target.name}.reserve"
    with reserve.open("x", encoding="utf-8"):
        pass
    try:
        if target.exists():
            raise FileExistsError(str(target))
        source.replace(target)
    finally:
        reserve.unlink(missing_ok=True)


def deliver(box: Path, sender: str, text: str) -> str:
    part = box / "tmp" / f"{os.getpid()}-{secrets.token_hex(6)}-{sender}.part"
    with part.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        current = stamp()
        count = 0
        while True:
            name = f"{current}-{sender}.md" if count == 0 else f"{current}-{sender}-{count}.md"
            try:
                place(part, box / "new" / name)
            except FileExistsError:
                fresh = stamp()
                if fresh != current:
                    current, count = fresh, 0
                else:
                    count += 1
            else:
                return name
    finally:
        part.unlink(missing_ok=True)
