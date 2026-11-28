from __future__ import annotations

import contextlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import runner

from orch_state import commands, herdr, relay_guard, start_steps, store

INPUT_MAX = 1_000_000
BLOCKED_TTL_MS = 600_000
PAUSED_TTL_MS = 1_800_000
CLEAR_EVENTS = frozenset({"SessionStart", "UserPromptSubmit", "PostToolUse"})
EVENT_STATES = {
    "SessionStart": "idle",
    "UserPromptSubmit": "working",
    "PreToolUse": "working",
    "PostToolUse": "working",
    "PermissionRequest": "needs-you",
    "Stop": "idle",
}
ASKING = frozenset({"permission_prompt", "elicitation_dialog"})
REQUEST_EVENTS = frozenset({"UserPromptSubmit", "PostToolUse", "Stop"})
TAIL_BYTES = 262_144
NAME_ENTRIES = (("custom-title", "customTitle"), ("agent-name", "agentName"))


def transcript_name(path: object) -> str | None:
    if not isinstance(path, str) or not path:
        return None
    try:
        with Path(path).open("rb") as handle:
            size = handle.seek(0, 2)
            handle.seek(max(0, size - TAIL_BYTES))
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        for kind, key in NAME_ENTRIES:
            if f'"{kind}"' not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            value = entry.get(key) if isinstance(entry, dict) else None
            if entry.get("type") == kind and isinstance(value, str) and value.strip():
                return store.clean(value, 40)
    return None


@dataclass(frozen=True)
class Action:
    labels: dict[str, str] | None
    ttl_ms: int | None


CLEAR = Action(None, None)


def first_word(tool_input: object) -> str:
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command")
    if not isinstance(command, str):
        return ""
    words = command.split()
    return words[0] if words else ""


def background(event: dict[str, object]) -> int:
    count = 0
    for key in ("background_tasks", "session_crons"):
        value = event.get(key)
        if isinstance(value, list | dict):
            count += len(value)
    return count


def plan(event: dict[str, object]) -> Action | None:
    name = event.get("hook_event_name")
    if name in CLEAR_EVENTS:
        return CLEAR
    if name == "PermissionRequest":
        tool = event.get("tool_name")
        tool = tool if isinstance(tool, str) else "tool"
        text = f"needs you: {tool} {first_word(event.get('tool_input'))}".strip()
        return Action({"blocked": text}, BLOCKED_TTL_MS)
    if name == "Stop":
        count = background(event)
        if count:
            text = f"paused: {count} background"
            return Action({"idle": text, "done": text}, PAUSED_TTL_MS)
        return CLEAR
    return None


def session_state(event: dict[str, object]) -> str | None:
    name = event.get("hook_event_name")
    if name == "Notification":
        return "needs-you" if event.get("notification_type") in ASKING else None
    return EVENT_STATES.get(name) if isinstance(name, str) else None


def write_state(event: dict[str, object], environ: dict[str, str], clock: store.Clock) -> None:
    state = session_state(event)
    session = event.get("session_id")
    if state is None or not isinstance(session, str) or not session:
        return
    where = event.get("cwd")
    cwd = Path(where) if isinstance(where, str) and where else Path.cwd()
    root = store.find(cwd, environ)
    if root is None:
        return
    changes: dict[str, object] = {
        "state": state,
        "state_at": store.stamp(clock),
        "project": store.project(cwd),
        **commands.process_fields(os.getppid()),
    }
    if event.get("hook_event_name") in REQUEST_EVENTS:
        changes["request_at"] = changes["state_at"]
    title = event.get("session_title")
    current = store.read(store.session_path(root, session)).get("name")
    if isinstance(title, str) and title.strip():
        named = store.clean(title, 40)
    elif not current:
        named = transcript_name(event.get("transcript_path"))
    else:
        named = None
    starting = event.get("hook_event_name") == "SessionStart"
    if starting:
        changes[start_steps.STARTED] = changes["state_at"]
    keeps_reserved = relay_guard.reserved(current)
    claims = relay_guard.reserved(named)
    if claims and starting and not keeps_reserved:
        claims_ok = not relay_guard.second_refused(root, session, clock)
    else:
        claims_ok = not claims
    if named and not keeps_reserved and claims_ok:
        changes["name"] = named
    store.save(root, session, changes, clock)


def remind(event: dict[str, object], environ: dict[str, str]) -> None:
    session, where = event.get("session_id"), event.get("cwd")
    if event.get("hook_event_name") != "UserPromptSubmit" or not isinstance(session, str):
        return
    cwd = Path(where) if isinstance(where, str) and where else Path.cwd()
    root = store.find(cwd, environ)
    line = start_steps.prompt_line(root, session) if root is not None and session else None
    if line:
        print(line)


def run(raw: str, environ: dict[str, str], clock: store.Clock = store.utc_now) -> None:
    event = json.loads(raw[:INPUT_MAX])
    if not isinstance(event, dict):
        return
    with contextlib.suppress(Exception):
        write_state(event, environ, clock)
    with contextlib.suppress(Exception):
        remind(event, environ)
    if environ.get("HERDR_ENV") != "1":
        return
    pane = herdr.pane_id(environ)
    if pane is None:
        return
    action = plan(event)
    if action is None:
        return
    found = herdr.binary(environ)
    if found is None:
        return
    herdr.report(herdr.argv(found, pane, action.labels, action.ttl_ms), environ)


def main() -> int:
    with contextlib.suppress(Exception):
        run(sys.stdin.read(INPUT_MAX + 1), runner.environ())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
