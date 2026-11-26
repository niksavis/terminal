from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

import runner
from orch_lessons.log import RefusedError

from orch_state import herdr, status, store

TEXT = "[orch keepalive] reply with one word: ok"
DUE_AFTER = timedelta(minutes=40)
COLD_AFTER = timedelta(minutes=55)
NEEDED = "needed"
CLOSE = "close"
AFTER_RESET = (NEEDED, CLOSE)
TIMEOUT_S = 5.0
NONE_NEEDED = (
    "orch keepalive found no session marked needed after the reset; mark each session that "
    "has work after the reset with: orch state set --session ID --after-reset needed"
)

Attempt = Callable[[list[str], float], runner.Done]


class Transport(Protocol):
    name: str

    def panes(self) -> dict[str, tuple[str, str]]: ...

    def send(self, target: str, text: str) -> str: ...


class Herdr:
    name = "herdr"

    def __init__(self, binary: str, attempt: Attempt = runner.attempt) -> None:
        self.binary = binary
        self.attempt = attempt

    def panes(self) -> dict[str, tuple[str, str]]:
        done = self.attempt([self.binary, "pane", "list"], TIMEOUT_S)
        if done.code != 0:
            raise RefusedError(f"herdr pane list failed: {(done.err or done.out).strip()[:200]}")
        try:
            listed = json.loads(done.out)["result"]["panes"]
        except ValueError, KeyError, TypeError:
            raise RefusedError("herdr pane list printed no pane list") from None
        found: dict[str, tuple[str, str]] = {}
        for pane in listed if isinstance(listed, list) else []:
            session = pane.get("agent_session") if isinstance(pane, dict) else None
            value = session.get("value") if isinstance(session, dict) else None
            if isinstance(value, str) and isinstance(pane.get("pane_id"), str):
                found[value] = (pane["pane_id"], str(pane.get("agent_status") or ""))
        return found

    def send(self, target: str, text: str) -> str:
        if text != TEXT:
            raise RefusedError(
                f"the herdr keep-alive adapter sends only its fixed text {TEXT!r}; "
                "text typed into a pane reads as the person's own words"
            )
        done = self.attempt([self.binary, "pane", "run", target, TEXT], TIMEOUT_S)
        return "" if done.code == 0 else ((done.err or done.out).strip() or "failed")[:200]


def transport(environ: dict[str, str]) -> Transport | None:
    found = herdr.binary(environ)
    return Herdr(found) if found else None


@dataclass
class Plan:
    due: list[tuple[str, str]] = field(default_factory=list)
    cold: list[str] = field(default_factory=list)
    waiting: list[str] = field(default_factory=list)
    close: list[str] = field(default_factory=list)


def _name(record: dict[str, object]) -> str:
    return store.clean(str(record.get("name") or record.get("id") or "?"), 40)


def request_age(record: dict[str, object], now: datetime) -> timedelta | None:
    when = status.when(record.get("request_at"))
    return now - when if when is not None else None


def _place(found: Plan, record: dict[str, object], now: datetime) -> None:
    name, age = _name(record), request_age(record, now)
    if record.get("state") == "working":
        found.waiting.append(f"{name} (working)")
    elif age is None:
        found.waiting.append(f"{name} (no request time yet)")
    elif age >= COLD_AFTER:
        found.cold.append(f"{name} (last request {status.age(age)} ago)")
    elif age >= DUE_AFTER:
        found.due.append((str(record.get("id")), name))
    else:
        found.waiting.append(f"{name} (last request {status.age(age)} ago)")


def plan(records: list[dict[str, object]], now: datetime, alive: status.Alive) -> Plan:
    live = [r for r in records if status.state(r, now, alive) != "dead"]
    needed = [r for r in live if r.get("after_reset") == NEEDED]
    if not needed:
        raise RefusedError(NONE_NEEDED)
    found = Plan()
    for record in needed:
        _place(found, record, now)
    found.close = [
        _name(r) for r in live if r.get("after_reset") != NEEDED and r.get("state") != "working"
    ]
    return found


def _report(found: Plan, head: str, failed: list[str]) -> str:
    lines = [head, *(f"ping failed: {one}" for one in failed)]
    if found.cold:
        lines.append(f"over {status.age(COLD_AFTER)}, cache likely cold: {', '.join(found.cold)}")
    if found.waiting:
        lines.append(f"not due: {', '.join(found.waiting)}")
    if found.close:
        lines.append(f"close after their handover: {', '.join(found.close)}")
    return "\n".join(lines)


def send(found: Plan, chosen: Transport | None) -> tuple[list[str], list[str]]:
    if not found.due:
        return [], []
    names = ", ".join(name for _, name in found.due)
    if chosen is None:
        raise RefusedError(
            f"orch keepalive has no transport adapter (herdr is not on PATH); send {TEXT!r} "
            f"as a cross-session message to: {names}"
        )
    panes = chosen.panes()
    sent: list[str] = []
    failed: list[str] = []
    for session, name in found.due:
        pane = panes.get(session)
        if pane is None:
            failed.append(f"{name} has no {chosen.name} pane; send it as a cross-session message")
        elif pane[1] == "working":
            failed.append(f"{name} is working in {chosen.name}; no ping needed")
        elif problem := chosen.send(pane[0], TEXT):
            failed.append(f"{name}: {problem}")
        else:
            sent.append(name)
    return sent, failed


def add_parser(groups: argparse._SubParsersAction) -> None:
    keep = groups.add_parser("keepalive")
    keep.add_argument("--dry-run", action="store_true")


def run(
    args: argparse.Namespace,
    root: Path,
    environ: dict[str, str],
    now: datetime,
    chosen: Transport | None = None,
) -> str:
    found = plan(store.sessions(root), now, store.alive)
    if args.dry_run:
        due = ", ".join(name for _, name in found.due) or "none"
        return _report(found, f"due for a ping: {due}", [])
    sent, failed = send(found, chosen if chosen is not None else transport(environ))
    return _report(found, f"pinged: {', '.join(sent) or 'none'}", failed)
