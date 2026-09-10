"""Every tracker operation a consumer needs that is not a create, a show or a list.

One operation per function, each taking a ledger directory and returning JSON-shaped data;
``cli.py`` owns the argument surface above it. The boundary is that split: nothing here
parses an argument and nothing there folds an event.

**Why it exists** (§4 in `SPEC.md`): the kit promised a tracker a repository can run
with nothing on PATH, and shipped three verbs. The engine reached ranking, the blocked set,
edges and deletion through these modules directly, so a consumer with no engine could
create a record and never advance one.

Every write holds the ledger's own lock across its read and its append, for the reason
``cli.create_record`` states. Kit rules are in `.basicly/core/kit/README.md`.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
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

# The field a record's labels live under, the separator one argv joins them with, and the
# split that gets them back. Declared in `label_shape.py` and re-exported rather than
# respelled: `fsck.py` checks the same shape and a second copy of the separator is how a
# checker and a writer come to disagree about one log (basicly-0cpn51).
LABELS_FIELD = label_shape.LABELS_FIELD
LABEL_SEPARATOR = label_shape.LABEL_SEPARATOR
labels_of = label_shape.labels_of

# The status a close moves a record to, and the field the reason lands under.
CLOSED_STATUS = "closed"
CLOSE_REASON_FIELD = "close_reason"


class TrackerCommandError(events.LedgerError):
    """An operation the ledger cannot carry out.

    A subclass of the ledger's own error so ``cli.main`` reports it on the path it already
    has, rather than growing a second handler the kit's one-class-per-handler rule forbids.
    """


def _ledger(directory: Path | str) -> Path:
    """*directory* as a ledger path.

    Raises:
        TrackerCommandError: it is not a directory. Refused rather than read as an empty
            ledger, so a mistyped path cannot answer "no such record".
    """
    ledger = Path(directory)
    if not ledger.is_dir():
        raise TrackerCommandError(str(ledger) + " is not a ledger directory")
    return ledger


def _require(ledger: Path, record: str) -> Any:
    """*record*'s folded state.

    Raises:
        TrackerCommandError: it is absent or tombstoned. A write against an absent id
            would otherwise mint a record under a name nobody chose.
    """
    state = events.fold(events.read_events(ledger)[0]).records.get(record)
    if state is None or state.tombstoned:
        raise TrackerCommandError("the ledger holds no record " + record)
    return state


def _append(
    ledger: Path, drafts: Sequence[Any], redact: Callable[[str], str] | None, lock: Any
) -> list:
    """Append *drafts* under a lock the caller already holds."""
    return events.append(ledger, list(drafts), redact=redact, held_lock=lock)


# --- the writes ----------------------------------------------------------------


def _resolved_labels(state: Any, add: Iterable[str], remove: Iterable[str]) -> str:
    """The record's label set after *add* and *remove*, in the joined storage form.

    Order is kept rather than sorted: a reordering reads as a change in every comparison.
    """
    labels = list(labels_of(state.fields.get(LABELS_FIELD)))
    for name in _split_all(add):
        if name not in labels:
            labels.append(name)
    for name in _split_all(remove):
        if name in labels:
            labels.remove(name)
    return LABEL_SEPARATOR.join(labels)


def _split_all(values: Iterable[str]) -> list[str]:
    """Every non-empty label named across *values*, each of which may be a joined list."""
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
    """Set *record*'s fields, its status, or its labels.

    The whole call is one critical section because the label pair is a read-modify-write:
    resolving the set outside the lock loses a second writer's label.

    Raises:
        TrackerCommandError: the ledger holds no such record, or nothing was asked for.
    """
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
    """Move each of *records* to the closed status, recording *reason* as a field.

    Every id under one lock, so a close naming several either lands whole or not at all.

    Raises:
        TrackerCommandError: the ledger holds no such record, or none was named.
    """
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
    """Append one prose entry to *record*'s work log.

    Written as :data:`events.KIND_NOTE`, the kind that carries prose (basicly-vkh0.30). The
    **command** keeps the external tracker's word because its name is a consumer surface and
    moves under its own deprecation window; the kind is not, so it moves now.

    Raises:
        TrackerCommandError: the ledger holds no such record, or the body is empty. An
            empty entry records nothing and is indistinguishable from a lost one.
    """
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
    """Record an edge from *record* to *target*, on the dependent — where the fold reads it.

    Refused when it would close a cycle, because a cycle makes the ready set undefined:
    every record on it waits for another on it, so none is ever dispatchable and nothing
    reports why.

    Raises:
        TrackerCommandError: either end is absent, the type is empty, or the edge closes a
            cycle.
    """
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
    """Refuse an edge whose target already reaches *record* over edges of the same type.

    Same-type only: a ``blocks`` path and a ``parent-child`` path crossing is a shape the
    graph is meant to hold, and refusing it would refuse an ordinary decomposition.

    Raises:
        TrackerCommandError: *target* already reaches *record*.
    """
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
    """Tombstone *record*, which is how an append-only log expresses a removal.

    The record and its history stay, every read treats it as absent, and its id is never
    minted again (`ids.minted_ever`).

    Raises:
        TrackerCommandError: the ledger holds no such record, or already tombstoned it.
    """
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
    """Mint a root id under *prefix* and append the record's first two events.

    Two events rather than one, because status is its own kind: the fold reads status only
    from a ``status`` event, so a record written without one answers no query.

    Raises:
        events.LockUnavailableError: another writer held the ledger. Retryable.
        ids.IdSpaceExhaustedError: no free id under *prefix*.
    """
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
    """Mint the next child id under *parent* and append the record with its edge.

    Minting reads every id the ledger ever held, so the mint and the append are one
    critical section — a writer in between could be handed the same id.

    Raises:
        TrackerCommandError: the ledger holds no such parent.
    """
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
