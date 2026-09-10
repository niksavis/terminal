"""Run the configured full checks before a push, and refuse one that would race a landing.

Invoked by the pre-push hook (via pre-commit or lefthook). Runs the
``[[verify.checks]]`` declared for mode ``full`` in the repo's basicly.toml —
the same deterministic gate the harness loop's verify phase uses, so a push is
held to exactly what the repo configures (and nothing it doesn't have).

**Why this hook also asks about the ledger.** ``pre-commit`` stashes the unstaged tree for
this stage; a landing writing the ledger inside that window makes the restore conflict, and
the push dies naming the stash rather than the contention. The refusal below names the
holder instead (basicly-u3b65o).

It cannot *prevent* the stash: ``pre-commit`` enters ``staged_files_only`` before any hook
of the stage runs, so this already executes inside the window and the refusal only shortens
it from the length of the full checks to one lock read (measured basicly-6ajmrc). Closing
the window is the ledger guard ``hooks.apply_pre_push_guard`` writes into the installed
pre-push hook, which is upstream of ``pre-commit`` and therefore of the stash.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_runner import project_root, run_checks

# Sibling *inside the managed core*, so the two relocate together. The lock's name and its
# liveness rule are read from the kit rather than respelled.
_EVENTS_SOURCE = Path(__file__).resolve().parent.parent / "kit" / "tracker" / "events.py"

# Spelled here as `tracker-path-scan.py` spells it: a hook cannot import `basicly`. A repo
# that redirected its ledger keeps the old behaviour, because the file is simply absent.
_LEDGER_DIR = Path(".basicly") / "ledger"


def _kit_events() -> Any:
    """The kit's ``events`` module, or None when it is not installed beside this hook.

    None rather than a raise: a repo that never adopted the store has no ledger to race.
    """
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
    """The pid of a live ledger write in flight, or None when the tree is quiet.

    None for every shape that is not a live holder: no kit, no lock, an unreadable lock, a
    dead pid, and a pid the platform cannot judge — Windows has no stdlib probe, so
    `events.default_pid_liveness` answers None there. Unknown is quiet on purpose: the
    hook's own uncertainty must not read as contention.
    """
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
    """Entry point for the pre-push hook."""
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
