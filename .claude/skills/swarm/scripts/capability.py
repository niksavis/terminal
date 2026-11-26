from __future__ import annotations

import json
import math
import os
import re
import stat
import sys
import time
from collections.abc import Mapping
from pathlib import Path

FORMAT = "basicly.capabilities"
VERSION = 1
DIR_ENV = "BASICLY_CAPABILITIES_DIR"
FOLDER = "capabilities"
WRITER = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
SIZE_MAX = 65536
FRESH_S = 7 * 24 * 3600
AHEAD_S = 300


def folder(environ: Mapping[str, str], platform: str, home: Path) -> Path:
    named = environ.get(DIR_ENV, "").strip()
    if named and Path(named).is_absolute():
        return Path(named)
    if platform == "win32":
        local = environ.get("LOCALAPPDATA", "").strip()
        return (Path(local) if local else home / "AppData" / "Local") / "basicly" / FOLDER
    state = environ.get("XDG_STATE_HOME", "").strip()
    base = Path(state) if state and Path(state).is_absolute() else home / ".local" / "state"
    return base / "basicly" / FOLDER


def _read(path: Path) -> object:
    try:
        shown = os.lstat(path)
        if not stat.S_ISREG(shown.st_mode) or shown.st_size > SIZE_MAX:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    except ValueError:
        return None


def _fresh(written: object, now: float) -> bool:
    if isinstance(written, bool) or not isinstance(written, (int, float)):
        return False
    return math.isfinite(written) and -AHEAD_S <= now - written <= FRESH_S


def _kinds(value: object, stem: str, now: float) -> list[str]:
    if not isinstance(value, dict):
        return []
    sound = (
        value.get("format") == FORMAT
        and value.get("version") == VERSION
        and value.get("writer") == stem
        and WRITER.fullmatch(stem) is not None
        and _fresh(value.get("written_at"), now)
    )
    renders = value.get("renders")
    kinds = renders.get("mermaid") if isinstance(renders, dict) else None
    if not sound or not isinstance(kinds, list):
        return []
    return kinds if all(isinstance(kind, str) for kind in kinds) else []


def drawn(
    kind: str,
    environ: Mapping[str, str] | None = None,
    now: float | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> bool:
    where = folder(
        os.environ if environ is None else environ,
        platform,
        Path.home() if home is None else home,
    )
    moment = time.time() if now is None else now
    try:
        paths = sorted(where.glob("*.json"))
    except OSError:
        return False
    return any(kind in _kinds(_read(path), path.stem, moment) for path in paths)
