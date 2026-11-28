from __future__ import annotations

from pathlib import Path

from orch_lessons.log import RefusedError

from orch_state import relay_guard, store

BRIEFED = "briefed_at"
STARTED = "started_at"
GATED = frozenset({"decide", "approve", "send", "report", "start"})
OPEN = (
    "orch status",
    "orch state set",
    "orch record",
    "orch accept",
    "orch brief",
    "ListAgents",
    "the read-only tracker commands",
)
REFUSAL = (
    "orch {group} refuses: this Orchestrator session has not run its start steps. "
    "Run orch brief first; it reads the orchestration record, its newest handover and "
    "the owner items. Open before it: {open}"
)
PROMPT_LINE = (
    "Start steps not done in this Orchestrator session: run orch brief before you answer "
    "the owner or relay anything, then read the orchestration rules and set the hourly "
    "flow check. orch decide, approve, send, report and start refuse until orch brief ran."
)


def briefed(record: dict[str, object]) -> bool:
    done, began = record.get(BRIEFED), record.get(STARTED)
    if not isinstance(done, str):
        return False
    return not isinstance(began, str) or done >= began


def pending(record: dict[str, object]) -> bool:
    return relay_guard.reserved(record.get("name")) and not briefed(record)


def _caller(cwd: Path, environ: dict[str, str]) -> tuple[Path, str] | None:
    root = store.find(cwd, environ)
    session = relay_guard.caller(environ)
    if root is None or not session:
        return None
    return root, session


def gate(group: str, cwd: Path, environ: dict[str, str]) -> None:
    if group not in GATED:
        return
    found = _caller(cwd, environ)
    if found is None:
        return
    root, session = found
    if pending(store.read(store.session_path(root, session))):
        raise RefusedError(REFUSAL.format(group=group, open=", ".join(OPEN)))


def mark(cwd: Path, environ: dict[str, str], clock: store.Clock = store.utc_now) -> None:
    found = _caller(cwd, environ)
    if found is None:
        return
    root, session = found
    if relay_guard.reserved(store.read(store.session_path(root, session)).get("name")):
        store.save(root, session, {BRIEFED: store.stamp(clock)}, clock)


def prompt_line(root: Path, session: str) -> str | None:
    return PROMPT_LINE if pending(store.read(store.session_path(root, session))) else None
