from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"the tracker kit's {file_name} is missing from beside vault_commit_hook.py"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
events = _load("events.py", "basicly_tracker_kit_events")
ids = _load("ids.py", "basicly_tracker_kit_ids")
vault_clone = _load("vault_clone.py", "basicly_tracker_kit_vault_clone")
vault_queue = _load("vault_queue.py", "basicly_tracker_kit_vault_queue")
vault_fold = _load("vault_fold.py", "basicly_tracker_kit_vault_fold")
vault_hooks = _load("vault_hooks.py", "basicly_tracker_kit_vault_hooks")

ACCEPTED = 0
REFUSED = 1
NONE_LINE = "Record: none"
MISS_KIND = "miss"
UNREACHABLE = "the vault could not be reached, so the claim was not checked"
_GIT_MERGE = re.compile(
    r"^Merge (?:branch|branches|remote-tracking branch|tag|commit|pull request) "
)
_ECHOES = ('Revert "', "fixup! ", "squash! ")
_TRAILING = re.compile(r"\(([^()\s]+)\)\s*$")
_RECORD_LINE = re.compile(r"^Record:\s*(\S+)\s*$", re.IGNORECASE)
_MAX_SUBJECT = 200
_UNREACHED = (ValueError, OSError, git_runner.GitRunnerError)
_UNSTAMPED = (OSError, ValueError)

Clock = Callable[[], float]


@dataclass(frozen=True)
class Commit:
    clone: Any
    state: Path
    message: Path
    session: str
    clock: Clock
    runner: Callable[..., str] = git_runner.run


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line.startswith("#")]


def _subject(text: str) -> str:
    return next((line.strip() for line in _lines(text) if line.strip()), "")


def _record_id(token: str) -> str | None:
    return token if ids.RECORD_ID_PATTERN.match(token) else None


def _named(text: str) -> str | None:
    found = _TRAILING.search(_subject(text))
    if found and _record_id(found.group(1)):
        return found.group(1)
    for line in _lines(text):
        trailer = _RECORD_LINE.match(line.strip())
        if trailer and trailer.group(1).lower() != "none" and _record_id(trailer.group(1)):
            return trailer.group(1)
    return None


def _says_none(text: str) -> bool:
    return any(
        (trailer := _RECORD_LINE.match(line.strip())) is not None
        and trailer.group(1).lower() == "none"
        for line in _lines(text)
    )


def _echoed(subject: str) -> str | None:
    echoed = None
    while True:
        prefix = next((p for p in _ECHOES if subject.startswith(p)), None)
        if prefix is None:
            return echoed
        subject = subject[len(prefix) :]
        if prefix.endswith('"'):
            subject = subject.removesuffix('"')
        echoed = subject


def _reached(commit: Commit) -> bool:
    folder = commit.clone.folder
    stamp = folder / vault_clone.FETCHED_NAME
    try:
        age = commit.clock() - float(stamp.read_text(encoding="utf-8").strip())
    except _UNSTAMPED:
        age = None
    if age is not None and 0 <= age < vault_hooks.FETCH_EVERY:
        return True
    try:
        fetched = vault_clone.fetch(
            commit.clone,
            clock=commit.clock,
            runner=commit.runner,
            timeout=vault_hooks.HOOK_DEADLINE,
            lock_wait=vault_hooks.HOOK_DEADLINE,
        )
    except events.LockUnavailableError:
        return True
    except _UNREACHED:
        return False
    return bool(fetched.get("fetched"))


def _held(folded: Any, writer: str, session: str) -> list[str]:
    if not session:
        return []
    return sorted(
        name
        for name, state in folded.records.items()
        if state.holder == (writer, session) and state.status != "closed"
    )


def _queued_claim(commit: Commit, writer: str, record: str) -> bool:
    return any(
        line.get("kind") == vault_fold.CLAIM
        and line.get("record") == record
        and line.get("writer") == writer
        and line.get("session") == commit.session
        for line in vault_queue.pending(commit.clone.folder / vault_queue.QUEUE_NAME)
    )


def _append_id(path: Path, record: str) -> str:
    text = path.read_bytes().decode("utf-8")
    kept = text.splitlines(keepends=True)
    for index, line in enumerate(kept):
        body = line.rstrip("\r\n")
        if body.strip() and not body.startswith("#"):
            kept[index] = f"{body.rstrip()} ({record}){line[len(body) :]}"
            break
    path.write_bytes("".join(kept).encode("utf-8"))
    return _subject("".join(kept))


def _miss(commit: Commit, record: str, subject: str) -> str:
    draft = {
        "kind": MISS_KIND,
        "record": record,
        "payload": {"subject": subject[:_MAX_SUBJECT], "why": UNREACHABLE},
    }
    origin = vault_queue.Origin(commit.session, False, commit.clock)
    return vault_queue.write(commit.clone, [draft], state=commit.state, origin=origin)["events"][0]


def _claim_command(record: str, url: str) -> str:
    return f"claim {record} --vault {url}"


def _judge(commit: Commit, folded: Any, writer: str, record: str) -> dict[str, object]:
    state = folded.records.get(record)
    mine = (writer, commit.session)
    if commit.session and state is not None and state.holder == mine:
        return {}
    if commit.session and _queued_claim(commit, writer, record):
        warning = f"the claim on {record} is unsettled: it has not reached the vault yet"
    else:
        warning = f"this session does not hold {record} in the vault"
    return {"warning": warning, "next": _claim_command(record, commit.clone.url)}


def _refusal(url: str, held: list[str]) -> dict[str, object]:
    return {
        "exit": REFUSED,
        "refused": (
            "the commit message names no record id; end the subject with (record-id), "
            f"or add the line {NONE_LINE!r} for a commit with no record"
        ),
        "held": held,
        "next": [_claim_command("RECORD", url), NONE_LINE],
    }


def check(commit: Commit) -> dict[str, object]:

    text = commit.message.read_bytes().decode("utf-8")
    subject = _subject(text)
    echoed = _echoed(subject)
    if _GIT_MERGE.match(subject) or echoed is not None:
        inherited = _named(echoed) if echoed is not None else None
        return {"exit": ACCEPTED, "exempt": subject.split(" ", 1)[0], "record": inherited}
    if _says_none(text):
        return {"exit": ACCEPTED, "record": None}
    reached = _reached(commit)
    writer = vault_queue.writer_of(commit.state)
    record = _named(text)
    folded = vault_fold.fold(vault_clone.valid_events(commit.clone))
    report: dict[str, object] = {"exit": ACCEPTED, "reached": reached}
    if record is None:
        held = _held(folded, writer, commit.session)
        if len(held) != 1:
            return {**_refusal(commit.clone.url, held), "reached": reached}
        record = held[0]
        subject = _append_id(commit.message, record)
        report["filled"] = record
    else:
        report.update(_judge(commit, folded, writer, record))
    report["record"] = record
    if not reached:
        report["miss"] = _miss(commit, record, subject)
    return report
