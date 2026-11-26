from __future__ import annotations

import importlib.util
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from orch_lessons.log import RefusedError
from orch_state import store

if TYPE_CHECKING:
    import runner

FOLDER = "failures"
PROMPT = "PROMPT"
USER = "USER"
REDACTOR = Path(".basicly/core/kit/tracker/redact.py")


def folder(base: Path) -> Path:
    return base / "delegations" / FOLDER


def save(base: Path, vendor: str, argv: list[str], prompt: str, done: runner.Done) -> Path:
    where = folder(base)
    where.mkdir(parents=True, exist_ok=True)
    value = {
        "source": "captured",
        "vendor": vendor,
        "exit_code": done.code,
        "argv": [PROMPT if part == prompt else part for part in argv],
        "stdout": done.out,
        "stderr": done.err,
        "at": store.utc_now().isoformat(timespec="seconds"),
    }
    stamp = store.utc_now().strftime("%Y%m%dT%H%M%SZ")
    path = where / f"{stamp}-{store.SAFE.sub('_', vendor)}-{uuid.uuid4().hex[:8]}.json"
    handle, name = tempfile.mkstemp(dir=where, prefix=".", suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(value, out, indent=2, sort_keys=True)
    Path(name).replace(path)
    return path


def _redactor(repo: Path) -> Any:
    path = repo / REDACTOR
    spec = importlib.util.spec_from_file_location("orch_failure_redact", path)
    if not path.is_file() or spec is None or spec.loader is None:
        raise RefusedError(
            f"{REDACTOR} is missing in {repo}; install the basicly tracker kit before a saved "
            "failure becomes a replay fixture"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def redact(value: dict[str, Any], repo: Path, user: str) -> dict[str, Any]:
    cleaned = _redactor(repo).event(value)
    if not user:
        return cleaned
    named = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(user)}(?![A-Za-z0-9_])")
    return json.loads(named.sub(USER, json.dumps(cleaned)))
