from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, NamedTuple

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside claims.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


events = _load("events.py", "basicly_tracker_kit_events")

HOLDER_FIELD = events.HOLDER_FIELD
HELD_STATUSES = frozenset({"in_progress", "closed"})
_ID = re.compile(r"\b[a-z][a-z0-9]*-[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[0-9]+)*\b")


class UnclaimedError(events.LedgerError):
    pass


class CommitContext(NamedTuple):
    committer: str
    ledger: str
    cli: str
    installed: tuple[str, ...] = ()


def cited_id(token: str, states: Mapping[str, Any]) -> str:
    parts = token.split("-")
    for end in range(len(parts), 1, -1):
        if "-".join(parts[:end]) in states:
            return "-".join(parts[:end])
    return "-".join(parts[:2])


def named_ids(message: str, states: Mapping[str, Any]) -> list[str]:
    cited = {cited_id(token, states) for token in _ID.findall(message)}
    return sorted(record for record in cited if record in states)


def unknown_ids(message: str, states: Mapping[str, Any]) -> list[str]:
    prefixes = {record.split("-", 1)[0] for record in states}
    cited = {cited_id(token, states) for token in _ID.findall(message)}
    return sorted({
        record for record in cited if record not in states and record.split("-", 1)[0] in prefixes
    })


def _describe(states: Mapping[str, Any], record: str) -> str:
    state = states[record]
    holder = str(state.fields.get(HOLDER_FIELD) or "") or "nobody"
    status = state.status or "open"
    status += " (cancelled)" if state.fields.get("close_resolution") == "cancelled" else ""
    return f"{record} is {status} and held by {holder}"


def refuse_commit(
    states: Mapping[str, Any], message: str, changed: Iterable[str], context: CommitContext
) -> None:

    committer, ledger, cli, installed = context
    folders = (ledger.rstrip("/") + "/", *(one for one in installed if one.endswith("/")))
    files = {one for one in installed if not one.endswith("/")}
    code = [
        path
        for path in changed
        if path.strip() and not path.startswith(folders) and path not in files
    ]
    if not code:
        return
    if not states:
        raise UnclaimedError(
            f"this code commit has no record in the staged ledger {ledger}. File and claim "
            f"a record, then stage it with `git add {ledger}` and commit again"
        )
    ids = named_ids(message, states)
    if not committer:
        raise UnclaimedError(
            "no committer name: set git config user.name, which the claim records as the holder"
        )
    if any(
        states[record].status in HELD_STATUSES
        and states[record].fields.get("close_resolution") != "cancelled"
        and str(states[record].fields.get(HOLDER_FIELD) or "") == committer
        for record in ids
    ):
        return
    unknown = unknown_ids(message, states)
    if not ids and unknown:
        raise UnclaimedError(
            f"this commit names {', '.join(unknown)}, which the staged ledger {ledger} does not "
            f"hold. If you created it in this checkout, stage the ledger with `git add {ledger}` "
            f"and commit again"
        )
    named = "; ".join(_describe(states, record) for record in ids) or "it names no record id"
    target = ids[0] if ids else "<id>"
    raise UnclaimedError(
        f"this commit changes {len(code)} file(s) outside the ledger, but {committer} holds "
        f"none of the records it names in progress ({named}). Claim the record first: "
        f"{cli} claim {ledger} {target}"
    )
