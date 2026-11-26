from __future__ import annotations

import json
import re
from pathlib import Path

from orch_lessons import log
from orch_lessons.log import RefusedError
from orch_relay import record

QUERY = "[pace done]"
DONE = re.compile(
    r"^\[pace done\] .*?\bchange=(?P<change>-?[0-9.]+|unknown_crossed_reset)"
    r" type=(?P<type>\S+)(?: .*)? by=(?P<by>[a-z]+)$"
)
HEADER = f"{'type':<12} {'records':>7} {'mean %':>7} {'max %':>6} {'crossed reset':>13}"


def _texts(entry: dict[str, object]) -> list[str]:
    found = entry.get("comments", [])
    if not isinstance(found, list):
        return []
    texts = [c.get("text") if isinstance(c, dict) else c for c in found]
    return [t for t in texts if isinstance(t, str)]


def gather(tracker: record.Tracker) -> dict[str, list[float | None]]:
    shown = json.loads(tracker.runner([*tracker.base, "list", tracker.ledger, "--query", QUERY]))
    entries = shown.get("records", []) if isinstance(shown, dict) else []
    per_type: dict[str, list[float | None]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        matches = [m for t in _texts(entry) if (m := DONE.match(t)) is not None]
        if not matches:
            continue
        newest = matches[-1]
        change = newest["change"]
        cost = None if change == "unknown_crossed_reset" else float(change)
        per_type.setdefault(newest["type"], []).append(cost)
    return per_type


def table(per_type: dict[str, list[float | None]]) -> list[str]:
    if not per_type:
        return ["cost per record type: no [pace done] note with by= yet"]
    rows = ["cost per record type (five_hour percent per delivered record):", HEADER]
    for kind in sorted(per_type):
        found = per_type[kind]
        known = [c for c in found if c is not None]
        mean = f"{sum(known) / len(known):.1f}" if known else "-"
        top = f"{max(known):.1f}" if known else "-"
        crossed = len(found) - len(known)
        rows.append(f"{kind:<12} {len(found):>7} {mean:>7} {top:>6} {crossed:>13}")
    return rows


def lines(cwd: Path, tracker: record.Tracker | None = None) -> list[str]:
    try:
        found = tracker or record.Tracker(log.repo_root(cwd))
        return table(gather(found))
    except (RefusedError, OSError, ValueError) as error:
        return [f"cost per record type: not read ({error})"]
