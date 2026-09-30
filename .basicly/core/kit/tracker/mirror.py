from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

MIRROR_FILE = "mirror.json"
SOURCES = {"beads": (".beads/issues.jsonl", ".beads/beads.db", "br sync --flush-only")}

_HERE = Path(__file__).resolve().parent


class MirrorError(ValueError):
    pass


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside mirror.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def read(ledger: Path | str) -> dict[str, str] | None:

    path = Path(ledger) / MIRROR_FILE
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write(ledger: Path | str, source: str) -> Path:

    if source not in SOURCES:
        raise MirrorError(f"no mirror reads {source!r}; the sources are {', '.join(SOURCES)}")
    path = Path(ledger) / MIRROR_FILE
    path.write_text(json.dumps({"source": source, "export": SOURCES[source][0]}) + "\n", "utf-8")
    return path


def remove(ledger: Path | str) -> bool:

    path = Path(ledger) / MIRROR_FILE
    if not path.is_file():
        return False
    path.unlink()
    return True


def _statuses(ledger: Path) -> dict[str, str]:

    events = _load("events.py", "basicly_tracker_kit_events")
    folded = events.fold(events.read_events(ledger)[0]).records
    return {record: str(state.status or "") for record, state in folded.items()}


def _stale(root: Path, source: str) -> str:

    export, store, flush = SOURCES[source]
    exported, stored = root / export, root / store
    if (
        stored.is_file()
        and exported.is_file()
        and stored.stat().st_mtime > exported.stat().st_mtime
    ):
        return f"{store} is newer than {export}; run `{flush}` so the mirror sees every change"
    return ""


def sync(ledger: Path | str, root: Path | str, *, dry_run: bool = False) -> dict[str, object]:

    ledger, root = Path(ledger), Path(root)
    held = read(ledger)
    if held is None:
        raise MirrorError(
            f"{ledger} mirrors no other tracker, so there is nothing to sync; start a mirror "
            f"with `basicly-tracker init --mirror beads`"
        )
    beans = _load("beans.py", "basicly_tracker_kit_beans")
    before = _statuses(ledger)
    source = beans.Source(held["source"], root / held["export"])
    report = beans.import_backlog(ledger, source, dry_run=dry_run)
    after = before if dry_run else _statuses(ledger)
    changed = sorted(
        record for record, status in after.items() if record in before and before[record] != status
    )
    return {
        **report,
        "mirror": held["source"],
        "status_changed": [
            {"record": record, "was": before[record], "now": after[record]} for record in changed
        ],
        "stale": _stale(root, held["source"]),
    }


def claim_wanted(ledger: Path, start: str, end: bool, stream: Any) -> bool:

    if start and end:
        raise SystemExit("tracker: --mirror starts a mirror and --end-mirror ends one; pass one")
    if start:
        write(ledger, start)
    elif end and remove(ledger):
        stream.write("tracker: the mirror ended; the claim gate guards commits from now on\n")
    held = read(ledger)
    if held is None:
        return True
    stream.write(
        f"tracker: this ledger mirrors {held['source']}, which stays the source of truth, so no "
        f"claim gate is installed; run `sync` to re-import it, and `init --end-mirror` to end it\n"
    )
    return False


def add_arguments(parser: Any) -> None:
    parser.add_argument("--mirror", default="", help="mirror this tracker; it stays the truth")
    parser.add_argument("--end-mirror", action="store_true", help="end the mirror")
