from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

LIMIT = 20_000
NOTE_MAX = 1_500
HANDOVER_MAX = 8_000
HANDOVER = "[handover"
OWNER = "[owner"
NO_SESSIONS = "no session has written its state yet"


@dataclass(frozen=True)
class Note:
    at: str
    text: str


def notes(found: Sequence[dict[str, object]]) -> list[Note]:
    return [Note(str(note.get("at", "")), str(note.get("text", ""))) for note in found]


def _cut(text: str, room: int) -> str:
    flat = text.strip()
    return flat if len(flat) <= room else flat[: room - 3] + "..."


def _row(note: Note) -> str:
    return f"- {note.at[:16]} {_cut(note.text, NOTE_MAX)}"


def _size(lines: Sequence[str]) -> int:
    return len("\n".join(lines).encode("utf-8"))


def render(record: str, found: Sequence[Note], sessions: Sequence[str], limit: int = LIMIT) -> str:
    marks = [n for n, note in enumerate(found) if note.text.startswith(HANDOVER)]
    start = marks[-1] if marks else None
    later = list(found[start + 1 :]) if start is not None else list(found)
    owner = [note for note in later if note.text.startswith(OWNER)]
    head = [
        f"record: {record}",
        "",
        "handover:",
        _cut(found[start].text, HANDOVER_MAX) if start is not None else "none found",
        "",
        f"owner items ({len(owner)}):",
        *(_row(note) for note in owner),
        "",
        "sessions:",
        *(sessions or [NO_SESSIONS]),
        "",
    ]
    rows = [_row(note) for note in later if not note.text.startswith(OWNER)]
    total = len(rows)
    left = f"{total} older note(s) left out; read them with: tracker show {record}"
    while rows and _size([*head, f"later notes ({len(rows)} of {total}):", *rows, left]) > limit:
        rows.pop(0)
    tail = [f"{total - len(rows)} older note(s) left out; read them with: tracker show {record}"]
    return "\n".join([
        *head,
        f"later notes ({len(rows)} of {total}):",
        *rows,
        *(tail if len(rows) < total else []),
    ])
