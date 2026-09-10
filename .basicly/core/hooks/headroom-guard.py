"""Put a Python module's remaining ratchet room in context before it is edited.

Claude Code PreToolUse hook (basicly-zq9i2m.4). ``module-size`` and ``comment-density``
both bind at commit time, and ``.scripts/headroom.py`` is the read that sizes a change
*before* it is written. The `python` skill gives the command and was skipped anyway - three
times on 2026-08-14 (basicly-co64) and three more on 2026-09-04, each paid for by trimming
prose after a gate refused. Guidance that must bind becomes a hook, the precedent
``unsplit-loop-guard`` sets in ``hooks.yaml``.

**Allows every call.** Verified against code.claude.com/docs/en/hooks.md on 2026-09-04: a
PreToolUse hook's exit-0 stdout and stderr reach the debug log only and never the model, and
the one non-blocking outcome that does reach it is ``permissionDecision: "allow"`` with
``additionalContext``. So the figures are injected and the edit proceeds; blocking in order
to inform would need an escape hatch and would earn being switched off.

Silent unless :func:`headroom.is_tight` already says an ordinary unit's edit would cross a
bound, so it costs nothing on the modules with room. Fails open: any error allows the call,
because a bug in a guard must never stop an agent editing.
"""

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
    """The project root, from the env Claude Code sets, else this file's grandparent."""
    declared = os.environ.get("CLAUDE_PROJECT_DIR")
    if declared:
        return Path(declared)
    return Path(__file__).resolve().parents[3]


def _target(payload: dict) -> str | None:
    """The repo-relative Python path an Edit/Write-family call is about to touch, if any."""
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
    """`.scripts/headroom.py`, loaded by path because it is a script, not a package.

    It puts `.scripts` and `src` on `sys.path` itself at import time, so its own sibling
    imports resolve once it is executed.
    """
    target = root / ".scripts" / "headroom.py"
    spec = importlib.util.spec_from_file_location("headroom", target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {target}")
    module = importlib.util.module_from_spec(spec)
    # Registered before execution because `headroom` defines a dataclass, and
    # `dataclasses` resolves a field's type through `sys.modules[cls.__module__]` - which
    # is None for a module loaded by path and never registered, and raises there.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def room_for(root: Path, path: str) -> str | None:
    """``headroom.render`` for *path* when it is tight, else None.

    Both thresholds come from `headroom` rather than from a third opinion here:
    ``is_tight`` is measured over this repo's own rebaseline records.
    """
    headroom = _load_headroom(root)
    for measured in headroom.measure(root):
        if measured.path == path and headroom.is_tight(measured):
            return headroom.render(measured)
    return None


def allow(context: str | None = None) -> int:
    """Emit the allow decision, carrying *context* into the model's window when given."""
    decision: dict[str, object] = {"hookEventName": "PreToolUse", "permissionDecision": "allow"}
    if context is not None:
        decision["additionalContext"] = context
    print(json.dumps({"hookSpecificOutput": decision}))
    return 0


def main() -> int:
    """Read the PreToolUse payload from stdin and allow, with the figures when they matter."""
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
