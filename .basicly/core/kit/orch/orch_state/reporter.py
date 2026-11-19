from __future__ import annotations

import contextlib
import json
import sys
from dataclasses import dataclass

import runner

from orch_state import herdr

INPUT_MAX = 1_000_000
BLOCKED_TTL_MS = 600_000
PAUSED_TTL_MS = 1_800_000
CLEAR_EVENTS = frozenset({"SessionStart", "UserPromptSubmit", "PostToolUse"})


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


def run(raw: str, environ: dict[str, str]) -> None:
    if environ.get("HERDR_ENV") != "1":
        return
    pane = herdr.pane_id(environ)
    if pane is None:
        return
    event = json.loads(raw[:INPUT_MAX])
    if not isinstance(event, dict):
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
