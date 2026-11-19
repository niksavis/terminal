from __future__ import annotations

import shlex
from collections.abc import Mapping


def _plain(value: object) -> str:
    return " ".join(str(value or "").split())


def message(code: int, report: Mapping[str, object]) -> str:
    record = shlex.quote(_plain(report.get("record")))
    held = report.get("holder")
    holder = held if isinstance(held, Mapping) else {}
    name = _plain(holder.get("name")) or "another session"
    if code == 3 and holder:
        return f"{record} is held by {name}; run unassign {record} --take, then claim {record}"
    messages = {
        4: f"{record} is unsettled; run sync, then claim {record} again",
        5: f"the vault could not be reached for {record}; check its connection and run sync",
        6: f"the vault could not finish the request for {record}; run sync and retry",
        7: f"{record} is already held by this session; continue work on {record}",
    }
    if code in messages:
        return messages[code]
    fix = report.get("fix")
    if isinstance(fix, str) and fix:
        return _plain(fix)
    return "the vault refused the request; run status and correct the named input before retrying"


def ledger_form(verb: str, record: str, directory: str, text: str = "") -> str:
    subject = f"{verb} uses ledger-form input for {record} in a vault repository"
    if verb in {"resolve", "acknowledge-loss", "assign", "delete"}:
        argv = ["fsck", "--repair"]
        why = "is retired in vault mode"
        if verb == "assign":
            argv = ["claim", record]
            why = "has no vault assignment semantics"
        elif verb == "delete":
            argv = [
                "close",
                directory,
                record,
                "--resolution",
                "cancelled",
                "--reason",
                "State why this task is cancelled",
            ]
            why = "must preserve its history"
        return f"{subject} and {why}; nothing was written, run `{shlex.join(argv)}`"
    if verb in {"comment", "claim", "unassign"}:
        argv = [verb, record]
        if verb == "comment":
            argv += ["--text", _plain(text)]
        return f"{subject}; run `{shlex.join(argv)}` without the ledger directory argument"
    read = shlex.join(["show", directory, record, "--json"])
    return (
        f"{subject} and has no vault form yet; nothing was written, follow basicly-bebeo6k "
        f"and run `{read}` to inspect the record"
    )
