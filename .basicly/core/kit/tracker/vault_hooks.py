from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_hooks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
events = _load("events.py", "basicly_tracker_kit_events")
vault_clone = _load("vault_clone.py", "basicly_tracker_kit_vault_clone")
vault_queue = _load("vault_queue.py", "basicly_tracker_kit_vault_queue")
vault_share = _load("vault_share.py", "basicly_tracker_kit_vault_share")

FETCH_EVERY = 20.0
HOOK_DEADLINE = 3.0
BULK_SLOT = 180.0
WRITE_LOCK_WAIT = 0.2
END_LOCK_WAIT = 0.9
STARTS = ("session-start", "prompt")
ENDS = ("stop", "session-end")
EVENTS = STARTS + ENDS

Clock = Callable[[], float]


def _stamp(path: Path) -> float | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _age(path: Path, clock: Clock) -> float | None:
    stamp = _stamp(path)
    return None if stamp is None else round(max(0.0, clock() - stamp), 1)


def slot_due(clone: Any, clock: Clock) -> bool:
    age = _age(clone.folder / vault_share.SHARED_AT, clock)
    return age is None or age >= BULK_SLOT


def _queued(clone: Any) -> list[dict]:
    return vault_queue.pending(clone.folder / vault_queue.QUEUE_NAME)


_KEPT = (ValueError, OSError, events.LedgerError, git_runner.GitRunnerError)


def due_share(clone: Any, state: Path, clock: Clock, *, now: bool = False) -> dict | None:

    if not _queued(clone) or not (now or slot_due(clone, clock)):
        return None
    plan = vault_share.Plan(
        clock, urgent=not now, deadline_s=HOOK_DEADLINE, lock_wait=WRITE_LOCK_WAIT
    )
    try:
        return vault_share.share(clone, state, plan=plan)
    except _KEPT as exc:
        return {"skipped": str(exc), "queued": len(_queued(clone))}


def _fetch_if_stale(clone: Any, clock: Clock) -> dict | None:
    age = _age(clone.folder / vault_clone.FETCHED_NAME, clock)
    if age is not None and age < FETCH_EVERY:
        return None
    return vault_clone.fetch(clone, timeout=HOOK_DEADLINE, lock_wait=HOOK_DEADLINE, clock=clock)


def hook(event: str, clone: Any, state: Path, *, clock: Clock) -> dict[str, object]:

    if event not in EVENTS:
        raise ValueError(f"hook takes one of {', '.join(EVENTS)}; it got {event!r}")
    try:
        if event in STARTS:
            fetched = _fetch_if_stale(clone, clock)
            shared = due_share(clone, state, clock)
        else:
            fetched = None
            plan = vault_share.Plan(clock, lock_wait=END_LOCK_WAIT)
            try:
                shared = vault_share.share(clone, state, plan=plan)
            except events.LockUnavailableError:
                shared = {"deferred": "another share in this clone is running and takes the queue"}
    except _KEPT as exc:
        return {"hook": event, "skipped": str(exc), "queued": len(_queued(clone))}
    return {"hook": event, "fetched": fetched, "shared": shared, "queued": len(_queued(clone))}


def status(clone: Any, *, clock: Clock) -> dict[str, object]:

    queued = _queued(clone)
    times = [at for line in queued if isinstance(at := line.get("at"), (int, float))]
    seen = {
        writer: {**last, "age_s": round(clock() - last["at"], 1) if last.get("at") else None}
        for writer, last in vault_clone.writers(clone).items()
    }
    known = (clone.bare / "HEAD").is_file()
    stuck = vault_clone.unrepaired(clone, git_runner.run, HOOK_DEADLINE) if known else {}
    return {
        "fetch_age_s": _age(clone.folder / vault_clone.FETCHED_NAME, clock),
        "writers": seen,
        "queued": len(queued),
        "oldest_age_s": round(clock() - min(times), 1) if times else None,
        "pending": [_pending_entry(line, clock) for line in queued],
        "retracted": sorted(stuck),
    }


def _pending_entry(line: dict, clock: Clock) -> dict[str, object]:
    carried = line.get("ledger")
    at = line.get("at")
    return {
        "queue_id": line.get("id"),
        "kind": line.get("kind"),
        "record": line.get("record"),
        "event": carried.get("id") if isinstance(carried, dict) else None,
        "age_s": round(clock() - at, 1) if isinstance(at, (int, float)) else None,
    }
