from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from orch_lessons.log import MARKER

FORMAT = 1
PROCESS_PLATFORM = "linux"
PROCESS_FIELDS = ("pid", "pid_start")
ROOT_ENV = "ORCH_STATE_ROOT"
SESSIONS = "sessions"
ASKS = "asks"
STATES = ("working", "needs-you", "idle")
TEXT_MAX = 200
VENDORS = ("claude", "codex", "copilot")
ANCESTORS = 8
SAFE = re.compile(r"[^A-Za-z0-9._-]")
GITDIR = re.compile(r"gitdir:\s*(?P<path>.+)")

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def clean(text: str, limit: int = TEXT_MAX) -> str:
    kept = "".join(" " if unicodedata.category(ch).startswith("C") else ch for ch in text)
    return " ".join(kept.split())[:limit]


def find(start: Path, environ: dict[str, str]) -> Path | None:
    named = environ.get(ROOT_ENV, "")
    if named:
        return Path(named) if Path(named).is_dir() else None
    for folder in (start, *start.parents):
        base = folder / ".orchestrator"
        if (base / "lessons" / MARKER).is_file():
            return base
    return None


def project(cwd: Path) -> str:
    for folder in (cwd, *cwd.parents):
        marker = folder / ".git"
        if marker.is_dir():
            return folder.name
        if marker.is_file():
            found = GITDIR.match(marker.read_text(encoding="utf-8").strip())
            if found is None:
                return folder.name
            common = Path(found["path"])
            if common.parent.name == "worktrees":
                return common.parent.parent.parent.name
            return folder.name
    return cwd.name


def _stat(pid: int) -> tuple[str, int, int] | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    name = text[text.index("(") + 1 : text.rindex(")")]
    rest = text[text.rindex(")") + 2 :].split()
    return name, int(rest[1]), int(rest[19])


def vendor_process(start: int) -> tuple[int, int, str] | None:
    pid = start
    for _ in range(ANCESTORS):
        found = _stat(pid)
        if found is None:
            return None
        name, parent, began = found
        vendor = next((v for v in VENDORS if name.startswith(v)), None)
        if vendor is not None:
            return pid, began, vendor
        if parent <= 1:
            return None
        pid = parent
    return None


def started(pid: int) -> int:
    found = _stat(pid) if Path("/proc/self/stat").is_file() else None
    return found[2] if found is not None else 0


def alive(pid: int, began: int) -> bool | None:
    if not Path("/proc/self/stat").is_file():
        return None
    found = _stat(pid)
    return found is not None and found[2] == began


def _path(folder: Path, key: str) -> Path:
    return folder / f"{SAFE.sub('_', key)[:80]}.json"


def session_path(base: Path, session: str) -> Path:
    return _path(base / SESSIONS, session)


def read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _replace(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(value, out, ensure_ascii=False, sort_keys=True)
        Path(name).replace(path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def stamp(clock: Clock) -> str:
    return clock().isoformat(timespec="seconds")


def _process_pair(record: dict[str, object], platform: str) -> dict[str, object]:
    pair = [record.get(k) for k in PROCESS_FIELDS]
    if platform == PROCESS_PLATFORM and all(isinstance(v, int) for v in pair):
        return record
    return {k: v for k, v in record.items() if k not in PROCESS_FIELDS}


def save(
    base: Path,
    session: str,
    changes: dict[str, object],
    clock: Clock,
    platform: str = sys.platform,
) -> dict[str, object]:
    path = _path(base / SESSIONS, session)
    record = {**read(path), **{k: v for k, v in changes.items() if v is not None}}
    record.update({"v": FORMAT, "id": session, "platform": platform, "updated_at": stamp(clock)})
    record = _process_pair(record, platform)
    _replace(path, record)
    return record


def sessions(base: Path) -> list[dict[str, object]]:
    folder = base / SESSIONS
    if not folder.is_dir():
        return []
    return [r for r in (read(p) for p in sorted(folder.glob("*.json"))) if r]


def ask(base: Path, record: str, question: str, options: str | None, clock: Clock) -> None:
    value: dict[str, object] = {
        "v": FORMAT,
        "record": record,
        "question": clean(question),
        "opened_at": stamp(clock),
    }
    if options:
        value["options"] = clean(options)
    _replace(_path(base / ASKS, record), value)


def close_ask(base: Path, record: str, how: str, clock: Clock) -> bool:
    path = _path(base / ASKS, record)
    value = read(path)
    if not value or "closed_at" in value:
        return False
    _replace(path, {**value, "v": FORMAT, "closed_at": stamp(clock), "closed_by": how})
    return True


def asks(base: Path) -> list[dict[str, object]]:
    folder = base / ASKS
    if not folder.is_dir():
        return []
    return [a for a in (read(p) for p in sorted(folder.glob("*.json"))) if a]
