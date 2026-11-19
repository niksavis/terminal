from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

CLAIM = "claim"
TAKE = "take"
UNASSIGN = "unassign"
STATUS = "status"
CONFIG = "config"
KNOWN_KINDS = frozenset({CLAIM, TAKE, UNASSIGN, STATUS, CONFIG, "comment", "segment", "ended"})
DEFAULT_STATUSES = frozenset({"open", "in_progress", "blocked", "closed"})
HOLDER_NAME = "name"


@dataclass
class Record:
    record: str
    holder: tuple | None = None
    name: str = ""
    status: str = "open"
    void: list = field(default_factory=list)
    upgrade_needed: str = ""


@dataclass
class Fold:
    records: dict = field(default_factory=dict)
    statuses: frozenset = DEFAULT_STATUSES

    def record(self, name: str) -> Record:
        return self.records.setdefault(name, Record(name))


class UpgradeNeededError(ValueError):
    pass


def _holder(event: Mapping[str, object]) -> tuple:
    return (str(event.get("writer") or ""), str(event.get("session") or ""))


def _name(event: Mapping[str, object]) -> str:
    payload = event.get("payload")
    named = payload.get(HOLDER_NAME) if isinstance(payload, Mapping) else None
    return named if isinstance(named, str) and named.isprintable() else ""


def holder_name_of(event: Mapping[str, object]) -> str:
    return _name(event)


def _void(state: Record, event: Mapping[str, object], why: str) -> None:
    state.void.append({"id": event.get("id"), "kind": event.get("kind"), "why": why})


def _claim(state: Record, event: Mapping[str, object]) -> None:
    wanted = _holder(event)
    if state.holder is not None and state.holder != wanted:
        _void(state, event, f"held by {state.holder[0]}/{state.holder[1]}")
        return
    state.holder = wanted
    state.name = _name(event)
    state.status = "in_progress"


def _unassign(state: Record, event: Mapping[str, object]) -> None:
    if state.holder is not None and state.holder != _holder(event):
        _void(state, event, "only the holder gives a record back")
        return
    payload = event.get("payload")
    target = payload.get("to") if isinstance(payload, Mapping) else None
    state.holder = tuple(target) if isinstance(target, (list, tuple)) and len(target) == 2 else None
    state.name = ""


def _status(fold: Fold, state: Record, event: Mapping[str, object]) -> None:
    payload = event.get("payload")
    wanted = payload.get("status") if isinstance(payload, Mapping) else None
    if wanted not in fold.statuses:
        _void(state, event, f"status {wanted!r} is not in the configuration in force")
        return
    state.status = str(wanted)


def _config(fold: Fold, event: Mapping[str, object]) -> None:
    payload = event.get("payload")
    statuses = payload.get("statuses") if isinstance(payload, Mapping) else None
    if isinstance(statuses, list) and statuses and all(isinstance(s, str) for s in statuses):
        fold.statuses = frozenset(statuses)


def fold(events: Iterable[Mapping[str, object]]) -> Fold:

    folded = Fold()
    for event in events:
        kind = str(event.get("kind") or "")
        if kind == CONFIG:
            _config(folded, event)
            continue
        name = event.get("record")
        if not isinstance(name, str) or not name:
            continue
        state = folded.record(name)
        if kind == CLAIM:
            _claim(state, event)
        elif kind == TAKE:
            state.holder = _holder(event)
            state.name = _name(event)
        elif kind == UNASSIGN:
            _unassign(state, event)
        elif kind == STATUS:
            _status(folded, state, event)
        elif kind not in KNOWN_KINDS and event.get("fold") is True:
            state.upgrade_needed = kind
    return folded


def refuse_a_holder_change(state: Record) -> None:

    if state.upgrade_needed:
        raise UpgradeNeededError(
            f"{state.record} holds a {state.upgrade_needed!r} event this tracker cannot fold; "
            "upgrade with `uv tool install --force` and the newest basicly tag, then run it again"
        )


def _shown(state: Record) -> dict[str, object] | None:
    if state.holder is None:
        return None
    return {"writer": state.holder[0], "session": state.holder[1], "name": state.name}


def view(state: Record) -> dict[str, object]:

    return {
        "record": state.record,
        "holder": _shown(state),
        "status": state.status,
        "void": list(state.void),
        "upgrade_needed": state.upgrade_needed or None,
    }
