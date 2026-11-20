from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    key = "basicly_tracker_kit_" + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, _HERE / (name + ".py"))
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's " + name + ".py is missing from beside it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


events = _load("events")
holders = _load("holders")
vault_write = _load("vault_write")


def _holder_draft(record: str, holder: str, take: bool) -> Any:

    if not holder:
        raise _load("commands").TrackerCommandError(
            "no holder name: set git config user.name, or name the holder with --to"
        )
    payload: dict[str, object] = {"name": holders.HOLDER_FIELD, "value": holder}
    if take:
        payload[holders.TAKE_KEY] = True
    return events.Draft(record, events.KIND_FIELD, payload)


def assign(
    directory: Path | str,
    record: str,
    holder: str,
    *,
    take: bool = False,
    context: Any = None,
) -> list:

    commands = _load("commands")
    ledger = commands._ledger(directory)
    drafts = [_holder_draft(record, holder, take)]
    with events.LedgerLock(ledger) as lock:
        commands._require(ledger, record)
        return commands._append(ledger, drafts, context, lock)


def claim(
    directory: Path | str,
    record: str,
    holder: str,
    *,
    take: bool = False,
    context: Any = None,
) -> list:

    commands = _load("commands")
    ledger = commands._ledger(directory)
    environ = commands.environment()
    if (landed := vault_write.claim(ledger, record, environ, context, take=take)) is not None:
        return landed
    drafts = [
        _holder_draft(record, holder, take),
        events.Draft(record, events.KIND_STATUS, {"status": "in_progress"}),
    ]
    with events.LedgerLock(ledger) as lock:
        state = commands._require(ledger, record)
        holders.refuse_a_claim_on_a_closed_record(state, ledger, record)
        return commands._append(ledger, drafts, context, lock)


def unassign(
    directory: Path | str,
    record: str,
    by: str,
    *,
    take: bool = False,
    context: Any = None,
) -> list:

    commands = _load("commands")
    ledger = commands._ledger(directory)
    environ = commands.environment()
    if (landed := vault_write.unassign(ledger, record, environ, context, take=take)) is not None:
        return landed
    with events.LedgerLock(ledger) as lock:
        holders.refuse_a_release_by_another(commands._require(ledger, record), record, by, take)
        payload: dict[str, object] = {"name": holders.HOLDER_FIELD, "value": ""}
        if take:
            payload[holders.TAKE_KEY] = True
        drafts = [events.Draft(record, events.KIND_FIELD, payload)]
        return commands._append(ledger, drafts, context, lock)


def _ready_refusal(state: Any, record: str, by: str, *, again: bool, clear: bool) -> str:
    holder = str(state.fields.get(holders.HOLDER_FIELD) or "")
    marked = str(state.fields.get(holders.READY_FIELD) or "")
    if state.status != holders.IN_PROGRESS:
        return (
            f"{record} is {state.status}; only an in_progress record waits for delivery; "
            f"claim it first"
        )
    if holder != by:
        return f"{record} is held by {holder or 'nobody'}, not by {by}; only its holder marks it"
    if clear and not marked:
        return f"{record} carries no ready mark; nothing to clear"
    if marked and not again and not clear:
        return (
            f"{record} is ready since {marked}; pass --again to mark it again after a change, "
            f"or --clear to remove the mark"
        )
    return ""


def mark_ready(
    directory: Path | str,
    record: str,
    by: str,
    *,
    mode: str = "",
    context: Any = None,
) -> list:

    commands = _load("commands")
    admitted, context = vault_write.admission(directory, context, commands.environment())
    ledger = commands._ledger(admitted)
    with events.LedgerLock(ledger) as lock:
        state = commands._require(ledger, record)
        clear = mode == "clear"
        if refused := _ready_refusal(state, record, by, again=mode == "again", clear=clear):
            raise commands.TrackerCommandError(refused)
        value = "" if clear else holders.READY_MARK
        payload = {"name": holders.READY_FIELD, "value": value}
        drafts = [events.Draft(record, events.KIND_FIELD, payload)]
        return commands._append(ledger, drafts, context, lock)
