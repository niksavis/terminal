from __future__ import annotations

import calendar
import importlib.util
import os
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside holders.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


events = _load("events.py", "basicly_tracker_kit_events")
fields = _load("fields.py", "basicly_tracker_kit_fields")

HOLDER_FIELD = events.HOLDER_FIELD
TAKE_KEY = events.TAKE_KEY
HOLDER_VARIABLE = "BASICLY_HOLDER"
NAME_VARIABLES = ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME")
USER_SECTION = "[user]"
HOLDER_SECTION = "[basicly]"
HOLDER_GIT_CONFIG = "git config basicly.holder"
SECONDS_PER_DAY = 86400


def _config_name(path: Path, section: str = USER_SECTION, name: str = "name") -> str:

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    inside = False
    for raw in lines:
        line = raw.strip()
        if line.startswith("["):
            inside = line.lower() == section
            continue
        key, sep, value = line.partition("=")
        if inside and sep and key.strip().lower() == name:
            return value.strip().strip('"')
    return ""


def _config_files(start: Path, environ: Mapping[str, str]) -> list[Path]:

    found: list[Path] = []
    git_dir = events._git_dir(start)
    if git_dir is not None:
        common = git_dir / "commondir"
        if common.is_file():
            git_dir = (git_dir / common.read_text(encoding="utf-8").strip()).resolve()
        found.append(git_dir / "config")
    home = Path(environ.get("HOME") or environ.get("USERPROFILE") or Path.home())
    xdg = environ.get("XDG_CONFIG_HOME")
    found.append((Path(xdg) if xdg else home / ".config") / "git" / "config")
    found.append(home / ".gitconfig")
    return found


def holder_and_source(
    start: Path | str, environ: Mapping[str, str] | None = None
) -> tuple[str, str]:

    values = os.environ if environ is None else environ
    if values.get(HOLDER_VARIABLE, "").strip():
        return values[HOLDER_VARIABLE].strip(), f"env {HOLDER_VARIABLE}"
    files = _config_files(Path(start).resolve(), values)
    for path in files:
        chosen = _config_name(path, HOLDER_SECTION, "holder")
        if chosen:
            return chosen, HOLDER_GIT_CONFIG
    for variable in NAME_VARIABLES:
        if values.get(variable, "").strip():
            return values[variable].strip(), f"env {variable}"
    for path in files:
        name = _config_name(path)
        if name:
            return name, "git config user.name"
    return "", "default"


def default_holder(start: Path | str, environ: Mapping[str, str] | None = None) -> str:

    return holder_and_source(start, environ)[0]


def _held_by(states: Mapping[str, Any], record: str) -> str:
    state = states.get(record)
    return str(state.fields.get(HOLDER_FIELD) or "") if state is not None else ""


def refuse(states: Mapping[str, Any], drafts: Sequence[Any]) -> None:

    for draft in drafts:
        if draft.kind != events.KIND_FIELD or draft.payload.get("name") != HOLDER_FIELD:
            continue
        wanted = str(draft.payload.get("value") or "")
        holder = _held_by(states, draft.record)
        if not wanted or not holder or holder == wanted or draft.payload.get(TAKE_KEY):
            continue
        since = states[draft.record].dates.get(events.DATE_ASSIGNED) or "an unknown time"
        raise fields.RefusedFieldError(
            f"{draft.record} is held by {holder} since {since}; ask them, or pass --take "
            f"to take it on purpose, which the ledger records"
        )


IN_PROGRESS = "in_progress"


def _kit_cli() -> str:

    script = _HERE / "cli.py"
    try:
        return script.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return script.as_posix()


def refuse_a_claim_on_a_closed_record(state: Any, ledger: Path, record: str) -> None:

    if state.status != events.CLOSING_STATUS:
        return
    reopen = f"python3 {_kit_cli()} update {ledger.as_posix()} {record} --status open"
    raise fields.RefusedFieldError(
        f"{record} is closed, and a claim never reopens a closed record; reopen it on "
        f"purpose with `{reopen}`, then claim it"
    )


def claimed_by(states: Mapping[str, Any], drafts: Sequence[Any], name: str) -> list:

    added = []
    for draft in drafts:
        if draft.kind != events.KIND_STATUS or draft.payload.get("status") != IN_PROGRESS:
            continue
        named = any(
            other.record == draft.record
            and other.kind == events.KIND_FIELD
            and other.payload.get("name") == HOLDER_FIELD
            for other in drafts
        )
        if name and not named and not _held_by(states, draft.record):
            added.append(
                events.Draft(draft.record, events.KIND_FIELD, {"name": HOLDER_FIELD, "value": name})
            )
    return [*drafts, *added]


def _seconds(stamp: object) -> float | None:

    if not isinstance(stamp, str) or not stamp:
        return None
    whole = stamp.rstrip("Z").partition(".")[0].partition("+")[0]
    return float(calendar.timegm(time.strptime(whole, "%Y-%m-%dT%H:%M:%S")))


def newest(states: Mapping[str, Any]) -> str:

    stamps = [state.dates.get(events.DATE_UPDATED) for state in states.values()]
    known = [stamp for stamp in stamps if _seconds(stamp) is not None]
    return max(known, key=lambda stamp: _seconds(stamp) or 0.0) if known else ""


def holding(state: Any, stale_days: int, ledger_now: str) -> dict[str, object] | None:

    holder = str(state.fields.get(HOLDER_FIELD) or "")
    if not holder and not state.contested:
        return None
    last = _seconds(state.dates.get(events.DATE_UPDATED))
    now = _seconds(ledger_now)
    stale = last is not None and now is not None and now - last > stale_days * SECONDS_PER_DAY
    return {
        "name": holder,
        "since": state.dates.get(events.DATE_ASSIGNED),
        "stale": stale,
        "contested": list(state.contested),
    }
