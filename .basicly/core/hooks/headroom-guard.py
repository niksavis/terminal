from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

REMEDY = (
    "Decide the placement now rather than trimming prose after a gate refuses: keep the "
    "change inside the room above, put the code in a module that has room, or declare the "
    "delta with a reason in `basicly.d/<record>.toml`. Never take a waiver to fit - it "
    "replaces the frozen entry and unratchets the module."
)


def _repo_root() -> Path:
    declared = os.environ.get("CLAUDE_PROJECT_DIR")
    if declared:
        return Path(declared)
    return Path(__file__).resolve().parents[3]


def _target(payload: dict) -> str | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw.endswith(".py"):
        return None
    try:
        return Path(raw).resolve().relative_to(_repo_root().resolve()).as_posix()
    except ValueError:
        return None


def _load_headroom(root: Path):

    target = root / ".scripts" / "headroom.py"
    spec = importlib.util.spec_from_file_location("headroom", target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def room_for(root: Path, path: str) -> str | None:

    headroom = _load_headroom(root)
    for measured in headroom.measure(root):
        if measured.path == path and headroom.is_tight(measured):
            return headroom.render(measured)
    return None


def allow(context: str | None = None) -> int:
    decision: dict[str, object] = {"hookEventName": "PreToolUse", "permissionDecision": "allow"}
    if context is not None:
        decision["additionalContext"] = context
    print(json.dumps({"hookSpecificOutput": decision}))
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError, UnicodeDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0
    path = _target(payload)
    if path is None:
        return 0
    try:
        rendered = room_for(_repo_root(), path)
    except Exception:  # noqa: BLE001 - fail open; naming the types would need `ratchet` imported
        return 0
    if rendered is None:
        return 0
    return allow(f"{rendered}\n{REMEDY}")


if __name__ == "__main__":
    raise SystemExit(main())
