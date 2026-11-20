from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from orch_lessons.log import RefusedError

from orch_state import store

ORCHESTRATOR = "Orchestrator"
CALLS = "relay-calls.jsonl"
HARNESS_ENV = "CLAUDE_CODE_SESSION_ID"
SESSION_LINE = "Session: Orchestrator ({short})"

Alive = Callable[[int, int], bool | None]


def reserved(name: object) -> bool:
    return isinstance(name, str) and name.strip().casefold() == ORCHESTRATOR.casefold()


def caller(environ: dict[str, str]) -> str:
    return environ.get(HARNESS_ENV, "")


def _log(root: Path, entry: dict[str, object]) -> None:
    with (root / CALLS).open("a", encoding="utf-8") as target:
        target.write(json.dumps(entry, sort_keys=True) + "\n")


def check(
    group: str, cwd: Path, environ: dict[str, str], clock: store.Clock = store.utc_now
) -> str:
    root = store.find(cwd, environ)
    if root is None:
        raise RefusedError(
            f"orch {group} needs the orchestrator store to prove the caller; "
            f"run it in the workspace, or set {store.ROOT_ENV}"
        )
    session = caller(environ)
    name = store.read(store.session_path(root, session)).get("name") if session else None
    accepted = name == ORCHESTRATOR
    _log(
        root,
        {
            "at": store.stamp(clock),
            "group": group,
            "session": session or None,
            "name": name,
            "accepted": accepted,
        },
    )
    if not accepted:
        who = f"the session named {name!r}" if name else "an unregistered session"
        raise RefusedError(
            f"orch {group} runs only in the session named {ORCHESTRATOR}; this is {who}. "
            "Send the request to the Orchestrator"
        )
    return SESSION_LINE.format(short=session[:8])


def live_orchestrators(root: Path, alive: Alive | None = None) -> list[str]:
    check = alive or store.alive
    folder = root / store.SESSIONS
    found = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        record = store.read(path)
        pid, began = record.get("pid"), record.get("pid_start")
        if not reserved(record.get("name")) or not isinstance(pid, int):
            continue
        if not isinstance(began, int) or check(pid, began) is not False:
            found.append(path.stem)
    return found


def second_refused(root: Path, session: str, clock: store.Clock) -> bool:
    others = [found for found in live_orchestrators(root) if found != session]
    if others:
        _log(
            root,
            {
                "at": store.stamp(clock),
                "group": "session-start",
                "session": session,
                "name": ORCHESTRATOR,
                "accepted": False,
                "reason": "second Orchestrator refused",
            },
        )
    return bool(others)


def registered(root: Path) -> set[str]:
    folder = root / store.SESSIONS
    if not folder.is_dir():
        return set()
    return {
        SESSION_LINE.format(short=path.stem[:8])
        for path in folder.glob("*.json")
        if store.read(path).get("name") == ORCHESTRATOR
    }
