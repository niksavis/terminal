"""What the ledger currently says: the ready set, the blocked set, and the totals.

The read half of the kit's operation surface, against ``commands.py``'s write half. The
boundary is the lock: nothing here takes one, so a query never blocks a writer.

**Why it exists** (§4 in `SPEC.md`): the engine reached ranking and readiness through
`scheduler` and `differential` directly, so a consumer with no engine had no way to ask
what to work on next. Kit rules are in `.basicly/core/kit/README.md`.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:
    """Load a sibling kit module by path, under the kit's fixed ``sys.modules`` name."""
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's " + file_name + " is missing from beside queries.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


differential = _load("differential.py", "basicly_tracker_kit_differential")
scheduler = _load("scheduler.py", "basicly_tracker_kit_scheduler")
snapshot = _load("snapshot.py", "basicly_tracker_kit_snapshot")
events = differential.events


def ledger_dir(directory: Path | str) -> Path:
    """*directory* as a ledger path.

    Raises:
        events.LedgerError: it is not a directory. Refused rather than read as an empty
            ledger, so a mistyped path cannot answer "no such record".
    """
    ledger = Path(directory)
    if not ledger.is_dir():
        raise events.LedgerError(str(ledger) + " is not a ledger directory")
    return ledger


def folded(directory: Path | str) -> dict[str, Any]:
    """Every record in the ledger at *directory*, folded."""
    return snapshot.load(ledger_dir(directory)).records


def read_record(directory: Path | str, record: str) -> dict[str, object] | None:
    """One record's folded state as JSON, or ``None`` when the ledger does not hold it."""
    state = folded(directory).get(record)
    return None if state is None else snapshot.record_to_dict(state)


def query_records(
    directory: Path | str, *, status: str | None = None, limit: int | None = None
) -> list[dict[str, object]]:
    """The ledger's records in id order, optionally narrowed to one *status*.

    Tombstoned records are left out. They stay in the fold on purpose — a delete is an
    event, not a removal — but a query is asking what the tracker currently holds, and
    ``show`` is still the way to read one back.
    """
    records = folded(directory)
    matched = [
        snapshot.record_to_dict(records[key])
        for key in sorted(records)
        if not records[key].tombstoned and (status is None or records[key].status == status)
    ]
    return matched if limit is None else matched[:limit]


def views_and_children(directory: Path | str) -> tuple:
    """The ledger's record views and its parent-child map, read once."""
    found = differential.read_ledger(ledger_dir(directory))
    views = differential.views_from_events(found)
    return views, differential.children_of(views, differential.DEFAULT_VOCABULARY)


def ready(directory: Path | str, limit: int | None = None) -> dict[str, object]:
    """The ready set in rank order, with the policy that produced it.

    The schema and sort travel with it: a rank recorded without its policy is
    uninterpretable later (`scheduler.Ranking`).
    """
    order = scheduler.ranking(ledger_dir(directory), limit=limit)
    return {
        "schema": order.schema,
        "sort": order.sort,
        "count": len(order.records),
        "records": [
            {"rank": row.rank, "score": row.score, "record": row.record, "title": row.title}
            for row in order.records
        ],
    }


def blocked(directory: Path | str) -> dict[str, object]:
    """Each dispatchable record that is not ready, and what holds it.

    Two reasons rather than one flag, because the repair differs: an open blocking edge is
    work to finish, and a parent-child child is a decomposition that made the parent an
    anchor. A blocking edge into a record the ledger does not hold is reported as unknown,
    never as satisfied.
    """
    vocabulary = differential.DEFAULT_VOCABULARY
    views, children = views_and_children(directory)
    rows = []
    for record in sorted(views):
        view = views[record]
        if view.tombstoned or not differential.is_dispatchable(view.status, vocabulary):
            continue
        if differential.is_ready(view, views, children, vocabulary):
            continue
        rows.append({
            "record": record,
            "status": view.status,
            "blocked_by": _open_blockers(view, views, vocabulary),
            "children": sorted(children.get(record) or ()),
        })
    return {"count": len(rows), "records": rows}


def _open_blockers(view: Any, views: Mapping[str, Any], vocabulary: Any) -> list:
    """The blocking edges of *view* whose target is not closed, with each target's status."""
    found = []
    for edge in view.dependencies:
        if edge.type not in vocabulary.blocking_types:
            continue
        target = views.get(edge.target)
        if target is None:
            found.append({"record": edge.target, "status": "unknown"})
        elif target.status not in vocabulary.closed_statuses:
            found.append({"record": edge.target, "status": target.status or ""})
    return sorted(found, key=lambda row: row["record"])


def stats(directory: Path | str) -> dict[str, object]:
    """The state of the backlog: counts by status, plus the ready and blocked counts."""
    ledger = ledger_dir(directory)
    folded = events.fold(events.read_events(ledger)[0]).records
    by_status: dict[str, int] = {}
    tombstoned = 0
    for state in folded.values():
        if state.tombstoned:
            tombstoned += 1
            continue
        key = state.status or "unset"
        by_status[key] = by_status.get(key, 0) + 1
    return {
        "records": len(folded) - tombstoned,
        "tombstoned": tombstoned,
        "by_status": dict(sorted(by_status.items())),
        "ready": ready(ledger)["count"],
        "blocked": blocked(ledger)["count"],
    }
