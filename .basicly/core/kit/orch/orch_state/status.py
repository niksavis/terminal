from __future__ import annotations

import unicodedata
from collections.abc import Callable
from datetime import datetime, timedelta

from orch_state.store import clean

WIDTH = 40
QUIET_AFTER = timedelta(minutes=15)
NUDGE_AFTER = timedelta(minutes=30)
STALE_AFTER = timedelta(hours=2)
ASK_STALE_AFTER = timedelta(hours=24)
NAME = 9
STATE = 9
AGE = 3

Alive = Callable[[int, int], bool | None]


def when(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def age(delta: timedelta) -> str:
    minutes = max(int(delta.total_seconds() // 60), 0)
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 48 * 60:
        return f"{minutes // 60}h"
    return f"{min(minutes // 1440, 99)}d"


def width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def fit(text: str, room: int) -> str:
    kept = ""
    for ch in text:
        if width(kept + ch) > room:
            break
        kept += ch
    return kept + " " * (room - width(kept))


def state(record: dict[str, object], now: datetime, alive: Alive) -> str:
    pid, began = record.get("pid"), record.get("pid_start")
    if isinstance(pid, int) and isinstance(began, int) and alive(pid, began) is False:
        return "dead"
    updated = when(record.get("updated_at"))
    if updated is None or now - updated >= STALE_AFTER:
        return "stale"
    if record.get("state") == "needs-you":
        return "needs you"
    if record.get("state") == "working" and now - updated < QUIET_AFTER:
        return "working"
    if now - updated >= NUDGE_AFTER:
        return "nudge"
    return "quiet"


def _now(record: dict[str, object], now: datetime) -> str:
    text = record.get("now")
    said = when(record.get("now_at"))
    if not isinstance(text, str) or not text or said is None:
        return ""
    if now - said >= QUIET_AFTER:
        return f"{age(now - said)} ago: {clean(text)}"
    return clean(text)


def _last(record: dict[str, object]) -> str:
    text = record.get("last")
    if not isinstance(text, str) or not text:
        return ""
    return f"last {'ok' if record.get('last_ok') is not False else 'failed'}: {clean(text)}"


def _request(record: dict[str, object], now: datetime) -> str:
    asked = when(record.get("request_at"))
    return f"request {age(now - asked)} ago" if asked is not None else ""


def _doing(record: dict[str, object], now: datetime) -> str:
    item = record.get("item")
    parts = [
        clean(item) if isinstance(item, str) and item else "",
        _request(record, now),
        _now(record, now),
        _last(record),
    ]
    return " | ".join(part for part in parts if part) or "-"


def row(record: dict[str, object], now: datetime, alive: Alive, columns: int = WIDTH) -> str:
    name = clean(str(record.get("name") or record.get("id") or "?"))
    updated = when(record.get("updated_at"))
    since = age(now - updated) if updated else "?"
    head = f"{fit(name, NAME)} {fit(state(record, now, alive), STATE)} {since:>{AGE}} "
    return (head + fit(_doing(record, now), max(columns, WIDTH) - width(head))).rstrip()


def header(asks: list[dict[str, object]], now: datetime) -> list[str]:
    open_now, old = 0, 0
    for item in asks:
        opened = when(item.get("opened_at"))
        if "closed_at" in item or opened is None:
            continue
        if now - opened >= ASK_STALE_AFTER:
            old += 1
        else:
            open_now += 1
    lines = []
    if open_now:
        noun = "decision waits" if open_now == 1 else "decisions wait"
        lines.append(f"{open_now} {noun} for you")
    if old:
        lines.append(f"{old} old ask(s) are stale (24 h)")
    return lines


def render(
    records: list[dict[str, object]],
    asks: list[dict[str, object]],
    now: datetime,
    alive: Alive,
    columns: int = WIDTH,
) -> list[str]:
    ordered = sorted(records, key=lambda r: str(r.get("name") or r.get("id") or ""))
    live = [r for r in ordered if state(r, now, alive) != "dead"]
    dead = len(ordered) - len(live)
    folded = [f"{dead} dead session(s) not shown"] if dead else []
    return [*header(asks, now), *(row(r, now, alive, columns) for r in live), *folded]
