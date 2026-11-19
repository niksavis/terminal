from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_queue.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
events = _load("events.py", "basicly_tracker_kit_events")
redact = _load("redact.py", "basicly_tracker_kit_redact")
vault_clone = _load("vault_clone.py", "basicly_tracker_kit_vault_clone")

QUEUE_NAME = "queue.jsonl"
WRITER_NAME = "writer.id"
SHARED_BY = "the next Stop or SessionEnd hook, or `share --vault` with the same vault"
_MAX_RECORD = 200


class QueueError(ValueError):
    pass


@dataclass(frozen=True)
class Origin:
    session: str
    immediate: bool
    clock: Callable[[], float]


def writer_of(state: Path) -> str:

    vault_clone.private(state)
    path = state / WRITER_NAME
    if not path.exists():
        draft = state / f"{WRITER_NAME}.{uuid.uuid4().hex}"
        handle = os.open(str(draft), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(f"{git_runner.new_writer_id()}\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(draft, path)
        except FileExistsError:
            pass
        finally:
            draft.unlink()
    try:
        return git_runner.writer_id(path.read_text(encoding="utf-8").strip())
    except git_runner.GitValueError:
        raise QueueError(f"{path} holds no writer id; move it away and run again") from None


def comment(record: str, body: str) -> dict[str, object]:

    if not record or len(record) > _MAX_RECORD or not record.isprintable():
        raise QueueError("comment --vault needs a record id of printable characters")
    if not body.strip():
        raise QueueError("comment --vault needs --text with the comment")
    return {"kind": "comment", "record": record, "payload": {"text": body}}


def _cut_torn(queue: Path) -> dict[str, object] | None:

    if not queue.exists():
        return None
    with queue.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            return None
        stream.seek(-1, os.SEEK_END)
        if stream.read(1) == b"\n":
            return None
    data = queue.read_bytes()
    keep = data.rfind(b"\n") + 1
    lost = data[keep:].decode("utf-8", errors="replace")
    with queue.open("r+b") as stream:
        stream.truncate(keep)
        stream.flush()
        os.fsync(stream.fileno())
    return {"bytes": len(data) - keep, "start": redact.text(lost[:80])}


def _append(queue: Path, lines: Sequence[Mapping[str, object]]) -> None:
    text = "".join(json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n" for line in lines)
    with queue.open("ab") as stream:
        stream.write(text.encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())


def pending(queue: Path) -> list[dict[str, object]]:

    if not queue.exists():
        return []
    found = []
    for line in queue.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            found.append(value)
    return found


def requeue(clone: Any, lines: Sequence[Mapping[str, object]]) -> int:

    vault_clone.private(clone.folder)
    queue = clone.folder / QUEUE_NAME
    with events.LedgerLock(clone.folder):
        _cut_torn(queue)
        held = {str(line.get("id")) for line in pending(queue)}
        fresh = [line for line in lines if str(line.get("id")) not in held]
        _append(queue, fresh)
    return len(fresh)


HOLDER_KINDS = frozenset({"claim", "take"})
HOLDER_NAME = "name"


def _redacted(draft: Mapping[str, object]) -> dict[str, object]:

    line = dict(redact.event(dict(draft)))
    payload = draft.get("payload")
    if draft.get("kind") not in HOLDER_KINDS or not isinstance(payload, Mapping):
        return line
    named = payload.get(HOLDER_NAME)
    if isinstance(named, str) and isinstance(line.get("payload"), dict):
        line["payload"] = {**line["payload"], HOLDER_NAME: named}
    return line


def checked(drafts: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    lines = [_redacted(draft) for draft in drafts]
    for line in lines:
        if (
            len(json.dumps(line.get("payload"), ensure_ascii=False).encode("utf-8"))
            > events.MAX_TEXT_BYTES
        ):
            cap = events.MAX_TEXT_BYTES
            raise QueueError(f"the {line['kind']} is above {cap} bytes after redaction; shorten it")
    return lines


def write(
    clone: Any,
    drafts: Sequence[Mapping[str, object]],
    *,
    state: Path,
    origin: Origin,
) -> dict[str, object]:

    writer = writer_of(state)
    vault_clone.private(clone.folder)
    now = origin.clock()
    lines = [
        {
            **draft,
            "id": uuid.uuid4().hex,
            "writer": writer,
            "session": redact.text(origin.session),
            "at": now,
        }
        for draft in checked(drafts)
    ]
    queue = clone.folder / QUEUE_NAME
    asked = time.monotonic()
    with events.LedgerLock(clone.folder):
        waited = time.monotonic() - asked
        torn = _cut_torn(queue)
        _append(queue, lines)
    waiting = pending(queue)
    times = [at for line in waiting if isinstance(at := line.get("at"), (int, float))]
    return {
        "queued": len(lines),
        "events": [line["id"] for line in lines],
        "pending": len(waiting),
        "oldest_age_s": round(max(0.0, now - min(times)), 1) if times else 0.0,
        "share": "immediate" if origin.immediate else SHARED_BY,
        "torn": torn,
        "lock_wait_s": round(waited, 3),
    }
