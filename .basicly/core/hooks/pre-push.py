from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_runner import project_root, run_checks

_EVENTS_SOURCE = Path(__file__).resolve().parent.parent / "kit" / "tracker" / "events.py"

_LEDGER_DIR = Path(".basicly") / "ledger"


def _kit_events() -> Any:

    if not _EVENTS_SOURCE.is_file():
        return None
    spec = importlib.util.spec_from_file_location("basicly_tracker_kit_events", _EVENTS_SOURCE)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("basicly_tracker_kit_events", module)
    spec.loader.exec_module(module)
    return module


def ledger_write_holder(repo_root: Path) -> int | None:

    events = _kit_events()
    if events is None:
        return None
    lock = repo_root / _LEDGER_DIR / events.LOCK_NAME
    try:
        holder = json.loads(lock.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    pid = holder.get("pid") if isinstance(holder, dict) else None
    if not isinstance(pid, int):
        return None
    return pid if events.default_pid_liveness(pid) is True else None


def main() -> int:
    root = project_root()
    pid = ledger_write_holder(root)
    if pid is not None:
        print(
            f"pre-push: a ledger write is in flight (pid {pid}), so this push would race it.\n"
            "`pre-commit` stashes the unstaged tree for this stage and the landing changes it\n"
            "underneath, which surfaces as `Stashed changes conflicted with hook auto-fixes` —\n"
            "a message about the stash, not about the contention. Your commits are unaffected.\n"
            "Wait for the landing to finish, then push again.",
            file=sys.stderr,
        )
        return 1
    return run_checks(root, "full")


if __name__ == "__main__":
    sys.exit(main())
