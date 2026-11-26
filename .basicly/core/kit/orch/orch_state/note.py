from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

SESSION_ENVS = ("ORCH_SESSION_ID", "CLAUDE_CODE_SESSION_ID")
LIMIT = 200
PACE_BY = {"start": "claim", "done": "landing"}
KIT = Path(__file__).resolve().parents[1]


def note(
    cwd: Path,
    environ: Mapping[str, str],
    *,
    item: str | None = None,
    last: str | None = None,
    ok: bool = True,
) -> bool:
    session = next((environ[key] for key in SESSION_ENVS if environ.get(key)), "")
    if not session or not (item or last):
        return False
    if str(KIT) not in sys.path:
        sys.path.insert(0, str(KIT))
    try:
        store = importlib.import_module("orch_state.store")
        base = store.find(cwd, dict(environ))
        if base is None:
            return False
        now = datetime.now(UTC)
        changes: dict[str, object] = {}
        if item:
            changes["item"] = store.clean(item, LIMIT)
        if last:
            changes["last"] = store.clean(last, LIMIT)
            changes["last_at"] = now.isoformat(timespec="seconds")
            changes["last_ok"] = ok
        store.save(base, session, changes, lambda: now)
    except OSError, ValueError, ImportError:
        return False
    return True


def pace(cwd: Path, environ: Mapping[str, str], record: str, moment: str) -> bool:
    session = next((environ[key] for key in SESSION_ENVS if environ.get(key)), "")
    if not session or not record or moment not in PACE_BY:
        return False
    if str(KIT) not in sys.path:
        sys.path.insert(0, str(KIT))
    try:
        store = importlib.import_module("orch_state.store")
        if store.find(cwd, dict(environ)) is None:
            return False
        commands = importlib.import_module("orch_pace.commands")
        args = argparse.Namespace(record=record, moment=moment, by=PACE_BY[moment])
        return bool(commands.auto(cwd, dict(environ), args))
    except OSError, ValueError, ImportError:
        return False
