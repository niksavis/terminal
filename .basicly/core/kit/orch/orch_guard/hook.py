from __future__ import annotations

import json
import sys
from pathlib import Path

ROLE = "orchestrator"
WRITE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
BLOCK = 2


def repository(path: Path) -> Path | None:
    for folder in (path, *path.parents):
        if (folder / ".git").exists():
            return folder
    return None


def target(event: dict[str, object]) -> Path | None:
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    return Path(str(raw)) if raw else None


def refusal(event: dict[str, object]) -> str | None:
    if event.get("agent_type") != ROLE or event.get("agent_id"):
        return None
    if event.get("tool_name") not in WRITE_TOOLS:
        return None
    path, cwd = target(event), event.get("cwd")
    if path is None or not cwd:
        return None
    home = repository(Path(str(cwd)))
    owner = repository(path.parent)
    if home is None or owner is None or owner == home:
        return None
    return (
        f"orchestrator write guard: {path} belongs to the project repository {owner}, "
        f"not to the workspace {home}. The orchestrator does not implement. Send the exact "
        "change to that project's session instead."
    )


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    message = refusal(event)
    if message is None:
        return 0
    print(message, file=sys.stderr)
    return BLOCK


if __name__ == "__main__":
    raise SystemExit(main())
