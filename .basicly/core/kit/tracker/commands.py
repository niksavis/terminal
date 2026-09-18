from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's " + file_name + " is missing from beside commands.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


queries = _load("queries.py", "basicly_tracker_kit_queries")
label_shape = _load("label_shape.py", "basicly_tracker_kit_label_shape")
differential = queries.differential
events = differential.events
migrate = differential.migrate
ids = events.ids

LABELS_FIELD = label_shape.LABELS_FIELD
LABEL_SEPARATOR = label_shape.LABEL_SEPARATOR
labels_of = label_shape.labels_of

CLOSED_STATUS = "closed"
CLOSE_REASON_FIELD = "close_reason"


class TrackerCommandError(events.LedgerError):
    pass


def _ledger(directory: Path | str) -> Path:

    ledger = Path(directory)
    if not ledger.is_dir():
        raise TrackerCommandError(str(ledger) + " is not a ledger directory")
    return ledger


def _require(ledger: Path, record: str) -> Any:

    state = events.fold(events.read_events(ledger)[0]).records.get(record)
    if state is None or state.tombstoned:
        raise TrackerCommandError("the ledger holds no record " + record)
    return state


def _append(
    ledger: Path, drafts: Sequence[Any], redact: Callable[[str], str] | None, lock: Any
) -> list:
    return events.append(ledger, list(drafts), redact=redact, held_lock=lock)


def _resolved_labels(state: Any, add: Iterable[str], remove: Iterable[str]) -> str:

    labels = list(labels_of(state.fields.get(LABELS_FIELD)))
    for name in _split_all(add):
        if name not in labels:
            labels.append(name)
    for name in _split_all(remove):
        if name in labels:
            labels.remove(name)
    return LABEL_SEPARATOR.join(labels)


def _split_all(values: Iterable[str]) -> list[str]:
    found: list[str] = []
    for value in values:
        found.extend(part.strip() for part in value.split(LABEL_SEPARATOR) if part.strip())
    return found


def update(  # noqa: PLR0913 — one argument per thing an update can set; see the docstring
    directory: Path | str,
    record: str,
    *,
    fields: Mapping[str, object] | None = None,
    status: str = "",
    add_labels: Sequence[str] = (),
    remove_labels: Sequence[str] = (),
    redact: Callable[[str], str] | None = None,
) -> list:

    ledger = _ledger(directory)
    named = dict(fields or {})
    if not named and not status and not add_labels and not remove_labels:
        raise TrackerCommandError("update " + record + " asks for no change")
    with events.LedgerLock(ledger) as lock:
        state = _require(ledger, record)
        drafts = [
            events.Draft(record, events.KIND_FIELD, {"name": name, "value": value})
            for name, value in sorted(named.items())
        ]
        if add_labels or remove_labels:
            resolved = _resolved_labels(state, add_labels, remove_labels)
            drafts.append(
                events.Draft(record, events.KIND_FIELD, {"name": LABELS_FIELD, "value": resolved})
            )
        if status:
            drafts.append(events.Draft(record, events.KIND_STATUS, {"status": status}))
        return _append(ledger, drafts, redact, lock)


def close(
    directory: Path | str,
    records: Sequence[str],
    *,
    reason: str = "",
    redact: Callable[[str], str] | None = None,
) -> list:

    ledger = _ledger(directory)
    if not records:
        raise TrackerCommandError("close names no record")
    with events.LedgerLock(ledger) as lock:
        drafts = []
        for record in records:
            _require(ledger, record)
            if reason:
                drafts.append(
                    events.Draft(
                        record,
                        events.KIND_FIELD,
                        {"name": CLOSE_REASON_FIELD, "value": reason},
                    )
                )
            drafts.append(events.Draft(record, events.KIND_STATUS, {"status": CLOSED_STATUS}))
        return _append(ledger, drafts, redact, lock)


def comment(
    directory: Path | str,
    record: str,
    text: str,
    *,
    redact: Callable[[str], str] | None = None,
) -> list:

    ledger = _ledger(directory)
    if not text:
        raise TrackerCommandError("a comment on " + record + " needs a body")
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        return _append(
            ledger, [events.Draft(record, events.KIND_NOTE, {"text": text})], redact, lock
        )


def add_dependency(
    directory: Path | str,
    record: str,
    target: str,
    *,
    edge_type: str = "",
    redact: Callable[[str], str] | None = None,
) -> list:

    ledger = _ledger(directory)
    if not edge_type:
        edge_type = differential.DEFAULT_VOCABULARY.parent_child_type
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        _require(ledger, target)
        _refuse_cycle(ledger, record, target, edge_type)
        payload = {migrate.EDGE_FROM: record, migrate.EDGE_TO: target, migrate.EDGE_TYPE: edge_type}
        return _append(ledger, [events.Draft(record, migrate.KIND_EDGE, payload)], redact, lock)


def _refuse_cycle(ledger: Path, record: str, target: str, edge_type: str) -> None:

    views, _ = queries.views_and_children(ledger)
    seen = set()
    frontier = [target]
    while frontier:
        current = frontier.pop()
        if current == record:
            raise TrackerCommandError(
                "an edge "
                + record
                + " -> "
                + target
                + " of type "
                + edge_type
                + " closes a cycle, which leaves every record on it permanently unready"
            )
        if current in seen:
            continue
        seen.add(current)
        view = views.get(current)
        if view is None:
            continue
        frontier.extend(edge.target for edge in view.dependencies if edge.type == edge_type)


def delete(
    directory: Path | str,
    record: str,
    *,
    redact: Callable[[str], str] | None = None,
) -> list:

    ledger = _ledger(directory)
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        return _append(ledger, [events.Draft(record, events.KIND_TOMBSTONE, {})], redact, lock)


def create_root(
    directory: Path | str,
    fields: Mapping[str, object],
    *,
    prefix: str,
    status: str = "open",
    redact: Callable[[str], str] | None = None,
) -> list:

    ledger = Path(directory)
    ledger.mkdir(parents=True, exist_ok=True)
    with events.LedgerLock(ledger) as lock:
        folded = events.fold(events.read_events(ledger)[0])
        record = ids.mint_root_id(
            prefix,
            ids.minted_ever(
                [key for key, state in folded.records.items() if not state.tombstoned],
                [key for key, state in folded.records.items() if state.tombstoned],
            ),
        )
        drafts = [
            events.Draft(record, events.KIND_CREATED, dict(fields)),
            events.Draft(record, events.KIND_STATUS, {"status": status}),
        ]
        return _append(ledger, drafts, redact, lock)


def create_child(
    directory: Path | str,
    parent: str,
    fields: Mapping[str, object],
    *,
    status: str = "open",
    redact: Callable[[str], str] | None = None,
) -> list:

    ledger = _ledger(directory)
    with events.LedgerLock(ledger) as lock:
        _require(ledger, parent)
        folded = events.fold(events.read_events(ledger)[0])
        record = ids.next_child_id(parent, set(folded.records))
        edge = {
            migrate.EDGE_FROM: record,
            migrate.EDGE_TO: parent,
            migrate.EDGE_TYPE: differential.DEFAULT_VOCABULARY.parent_child_type,
        }
        drafts = [
            events.Draft(record, events.KIND_CREATED, dict(fields)),
            events.Draft(record, events.KIND_STATUS, {"status": status}),
            events.Draft(record, migrate.KIND_EDGE, edge),
        ]
        return _append(ledger, drafts, redact, lock)
