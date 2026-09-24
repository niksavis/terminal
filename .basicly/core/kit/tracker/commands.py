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
templates = _load("templates.py", "basicly_tracker_kit_templates")
writers = _load("writers.py", "basicly_tracker_kit_writers")
recurrence = _load("recurrence.py", "basicly_tracker_kit_recurrence")
values = _load("values.py", "basicly_tracker_kit_values")
holders = _load("holders.py", "basicly_tracker_kit_holders")
forks = _load("forks.py", "basicly_tracker_kit_forks")
edges = _load("edges.py", "basicly_tracker_kit_edges")
review = _load("review.py", "basicly_tracker_kit_review")
claims = _load("claims.py", "basicly_tracker_kit_claims")
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


def _is_repository(path: Path) -> bool:
    return (path / ".git").exists() or (path / ".basicly").is_dir()


def _holds_ledger(path: Path) -> bool:
    return (
        any(path.glob(events.LOG_GLOB))
        or any(path.glob(events.PENDING_GLOB))
        or (path / templates.TEMPLATE_FILE).is_file()
    )


def resolve_ledger(directory: Path | str, *, starts: bool = False) -> Path:

    given = Path(directory)
    if _is_repository(given):
        raise TrackerCommandError(
            f"{given} is a repository, not a ledger; name the ledger directory inside it"
        )
    if starts:
        return given
    if not given.is_dir():
        raise TrackerCommandError(f"{given} is not a ledger directory")
    if _holds_ledger(given) or not any(given.iterdir()):
        return given
    raise TrackerCommandError(
        f"{given} holds no ledger ({events.LOG_GLOB} or {events.PENDING_GLOB}); "
        f"name the ledger directory"
    )


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
    ledger: Path,
    drafts: Sequence[Any],
    redact: Callable[[str], str] | None,
    lock: Any,
    *,
    repeat: bool = False,
) -> list:
    template = templates.load(ledger)
    values.refuse(events, drafts, template)
    states = events.fold(events.read_events(ledger)[0]).records
    holders.refuse(states, drafts)
    review.refuse(states, drafts, writers.writer_class(), template)
    resolved = recurrence.at_the_generation_this_write_needs(
        events, ledger, drafts, repeat=repeat, redact=redact
    )
    return events.append(
        ledger, resolved, actor=writers.writer_class(), redact=redact, held_lock=lock
    )


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
    if_seq: int | None = None,
    claimant: str = "",
) -> list:

    ledger = _ledger(directory)
    named = dict(fields or {})
    if not named and not status and not add_labels and not remove_labels:
        raise TrackerCommandError("update " + record + " asks for no change")
    with events.LedgerLock(ledger) as lock:
        state = _require(ledger, record)
        if if_seq is not None:
            touched = {*named, *([LABELS_FIELD] if add_labels or remove_labels else [])}
            _refuse_stale(ledger, record, if_seq, touched | ({STATUS_NAME} if status else set()))
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
        drafts = holders.claimed_by({record: state}, drafts, claimant)
        return _append(ledger, drafts, redact, lock)


STATUS_NAME = "status"


def _refuse_stale(ledger: Path, record: str, if_seq: int, touched: set[str]) -> None:

    changed = sorted(
        {
            STATUS_NAME if event.kind == events.KIND_STATUS else str(event.payload.get("name"))
            for event in events.read_events(ledger)[0]
            if event.record == record
            and event.seq > if_seq
            and event.kind in (events.KIND_FIELD, events.KIND_STATUS)
        }
        & touched
    )
    if changed:
        raise TrackerCommandError(
            f"{record} changed {', '.join(changed)} after you read it at seq {if_seq}; "
            f"reload it and apply your edit again"
        )


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
        edges.refuse_edge(ledger, record, target, edge_type)
        edges.refuse_cycle(ledger, record, target, edge_type)
        payload = {migrate.EDGE_FROM: record, migrate.EDGE_TO: target, migrate.EDGE_TYPE: edge_type}
        return _append(ledger, [events.Draft(record, migrate.KIND_EDGE, payload)], redact, lock)


def remove_dependency(
    directory: Path | str,
    record: str,
    target: str,
    *,
    edge_type: str = "blocks",
    redact: Callable[[str], str] | None = None,
) -> list:

    ledger = _ledger(directory)
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        edges.refuse_retraction(queries.views_and_children(ledger)[0], record, target, edge_type)
        payload = {migrate.EDGE_FROM: record, migrate.EDGE_TO: target, migrate.EDGE_TYPE: edge_type}
        drafts = [events.Draft(record, events.KIND_EDGE_RETRACTED, payload)]
        return _append(ledger, drafts, redact, lock)


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


def migrate_fields(directory: Path | str, *, redact: Callable[[str], str] | None = None) -> list:

    ledger = _ledger(directory)
    shaping = values.fields.shaping
    with events.LedgerLock(ledger) as lock:
        states = events.fold(events.read_events(ledger)[0]).records
        drafts = []
        for record, state in sorted(states.items()):
            if state.tombstoned or state.status == CLOSED_STATUS:
                continue
            body = state.fields.get(shaping.DESCRIPTION_FIELD)
            text = body if isinstance(body, str) else ""
            for heading, name in shaping.SECTIONS:
                held = state.fields.get(name)
                entries = shaping.section_entries(text, heading) or tuple(
                    line for line in shaping.section_text(text, heading).splitlines() if line
                )
                if entries and not (isinstance(held, str) and held.strip()):
                    value = "\n".join(f"- {entry}" for entry in entries)
                    payload = {"name": name, "value": value}
                    drafts.append(events.Draft(record, events.KIND_FIELD, payload))
        return _append(ledger, drafts, redact, lock) if drafts else []


def _holder_draft(record: str, holder: str, take: bool) -> Any:

    if not holder:
        raise TrackerCommandError(
            "no holder name: set git config user.name, or name the holder with --to"
        )
    payload: dict[str, object] = {"name": holders.HOLDER_FIELD, "value": holder}
    if take:
        payload[holders.TAKE_KEY] = True
    return events.Draft(record, events.KIND_FIELD, payload)


def assign(
    directory: Path | str,
    record: str,
    holder: str,
    *,
    take: bool = False,
    redact: Callable[[str], str] | None = None,
) -> list:

    ledger = _ledger(directory)
    drafts = [_holder_draft(record, holder, take)]
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        return _append(ledger, drafts, redact, lock)


def claim(
    directory: Path | str,
    record: str,
    holder: str,
    *,
    take: bool = False,
    redact: Callable[[str], str] | None = None,
) -> list:

    ledger = _ledger(directory)
    drafts = [
        _holder_draft(record, holder, take),
        events.Draft(record, events.KIND_STATUS, {"status": "in_progress"}),
    ]
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        return _append(ledger, drafts, redact, lock)


def unassign(
    directory: Path | str, record: str, *, redact: Callable[[str], str] | None = None
) -> list:

    ledger = _ledger(directory)
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        payload = {"name": holders.HOLDER_FIELD, "value": ""}
        return _append(ledger, [events.Draft(record, events.KIND_FIELD, payload)], redact, lock)


def _restated(record: str, state: Any, key: str) -> list:

    if key == forks.STATUS_KEY:
        drafts = [events.Draft(record, events.KIND_STATUS, {"status": state.status})]
        if state.status == CLOSED_STATUS:
            reason = {"name": CLOSE_REASON_FIELD, "value": state.fields.get(CLOSE_REASON_FIELD)}
            drafts.insert(0, events.Draft(record, events.KIND_FIELD, reason))
        return drafts
    payload: dict[str, object] = {"name": key, "value": state.fields.get(key)}
    if key == holders.HOLDER_FIELD:
        payload[holders.TAKE_KEY] = True
    return [events.Draft(record, events.KIND_FIELD, payload)]


def resolve(
    directory: Path | str, record: str, *, redact: Callable[[str], str] | None = None
) -> list:

    ledger = _ledger(directory)
    with events.LedgerLock(ledger) as lock:
        state = _require(ledger, record)
        ordered = events.canonical_order(events.read_events(ledger)[0])
        keys = sorted({one["key"] for one in forks.of_record(ordered, record)})
        if not keys:
            raise TrackerCommandError(f"{record} has no unresolved conflict to resolve")
        drafts = [draft for key in keys for draft in _restated(record, state, str(key))]
        appended = _append(ledger, drafts, redact, lock, repeat=True)
        if not appended:
            raise TrackerCommandError(f"resolve {record} appended nothing, so the fork stays")
        return appended
