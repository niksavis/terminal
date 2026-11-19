from __future__ import annotations

import importlib.util
import os
import sys
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
        raise ImportError("the tracker kit's " + file_name + " is missing from beside commands.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


parent_progress = _load("parent_progress.py", "basicly_tracker_kit_parent_progress")
queries = _load("queries.py", "basicly_tracker_kit_queries")
label_shape = _load("label_shape.py", "basicly_tracker_kit_label_shape")
templates = _load("templates.py", "basicly_tracker_kit_templates")
writers = _load("writers.py", "basicly_tracker_kit_writers")
recurrence = _load("recurrence.py", "basicly_tracker_kit_recurrence")
values = _load("values.py", "basicly_tracker_kit_values")
holders = _load("holders.py", "basicly_tracker_kit_holders")
pin = _load("pin.py", "basicly_tracker_kit_pin")
forks = _load("forks.py", "basicly_tracker_kit_forks")
edges = _load("edges.py", "basicly_tracker_kit_edges")
review = _load("review.py", "basicly_tracker_kit_review")
claims = _load("claims.py", "basicly_tracker_kit_claims")
git_layout = _load("git_layout.py", "basicly_tracker_kit_git_layout")
vault_write = _load("vault_write.py", "basicly_tracker_kit_vault_write")
holder_writes = _load("holder_writes.py", "basicly_tracker_kit_holder_writes")
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


def environment() -> Mapping[str, str]:
    return os.environ


def _is_repository(path: Path) -> bool:
    return (path / ".git").exists() or (path / ".basicly").is_dir()


def _holds_ledger(path: Path) -> bool:
    return (
        any(path.glob(events.LOG_GLOB))
        or any(path.glob(events.PENDING_GLOB))
        or (path / templates.TEMPLATE_FILE).is_file()
    )


def resolve_ledger(directory: Path | str, *, starts: bool = False) -> Path:

    given = git_layout.shared_ledger(directory)
    _load("ledger_freeze.py", "basicly_tracker_kit_ledger_freeze").check_source(given)
    if _is_repository(given):
        raise TrackerCommandError(
            f"{given} is a repository, not a ledger; name the ledger directory inside it"
        )
    if starts:
        return given
    if vault_write.config_of(given) is not None:
        return given
    _ledger(given)
    if _holds_ledger(given) or not any(one.name != pin.PIN_FILE for one in given.iterdir()):
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
    context: Any,
    lock: Any,
    *,
    repeat: bool = False,
) -> list:
    write = vault_write.Write(ledger, context, lock, os.environ)
    return vault_write.land(write, drafts, repeat=repeat)


def update(  # noqa: PLR0913 — one argument per thing an update can set
    directory: Path | str,
    record: str,
    *,
    fields: Mapping[str, object] | None = None,
    status: str = "",
    add_labels: Sequence[str] = (),
    remove_labels: Sequence[str] = (),
    context: Any = None,
    if_seq: int | None = None,
    claimant: str = "",
) -> list:

    admitted, context = vault_write.admission(directory, context, environment())
    ledger = _ledger(admitted)
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
            resolved = label_shape.resolved_labels(state, add_labels, remove_labels)
            drafts.append(
                events.Draft(record, events.KIND_FIELD, {"name": LABELS_FIELD, "value": resolved})
            )
        if status:
            drafts.append(events.Draft(record, events.KIND_STATUS, {"status": status}))
        if not isinstance(context, vault_write.WriteContext) or context.target is None:
            drafts = holders.claimed_by({record: state}, drafts, claimant)
        return _append(ledger, drafts, context, lock)


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
    resolution: str = "completed",
    context: Any = None,
) -> list:

    admitted, context = vault_write.admission(directory, context, environment())
    ledger = _ledger(admitted)
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
            drafts.append(
                events.Draft(
                    record, events.KIND_FIELD, {"name": "close_resolution", "value": resolution}
                )
            )
            drafts.append(events.Draft(record, events.KIND_STATUS, {"status": CLOSED_STATUS}))
        return _append(ledger, drafts, context, lock)


def comment(
    directory: Path | str,
    record: str,
    text: str,
    *,
    context: Any = None,
) -> list:

    admitted, context = vault_write.admission(directory, context, environment())
    ledger = _ledger(admitted)
    if not text:
        raise TrackerCommandError("a comment on " + record + " needs a body")
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        return _append(
            ledger, [events.Draft(record, events.KIND_NOTE, {"text": text})], context, lock
        )


def add_dependency(
    directory: Path | str,
    record: str,
    target: str,
    *,
    edge_type: str = "",
    context: Any = None,
) -> list:

    admitted, context = vault_write.admission(directory, context, environment())
    ledger = _ledger(admitted)
    if not edge_type:
        edge_type = differential.DEFAULT_VOCABULARY.parent_child_type
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        _require(ledger, target)
        edges.refuse_edge(ledger, record, target, edge_type)
        edges.refuse_cycle(ledger, record, target, edge_type)
        payload = {migrate.EDGE_FROM: record, migrate.EDGE_TO: target, migrate.EDGE_TYPE: edge_type}
        return _append(ledger, [events.Draft(record, migrate.KIND_EDGE, payload)], context, lock)


def remove_dependency(
    directory: Path | str,
    record: str,
    target: str,
    *,
    edge_type: str = "blocks",
    context: Any = None,
) -> list:

    admitted, context = vault_write.admission(directory, context, environment())
    ledger = _ledger(admitted)
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        edges.refuse_retraction(queries.views_and_children(ledger)[0], record, target, edge_type)
        payload = {migrate.EDGE_FROM: record, migrate.EDGE_TO: target, migrate.EDGE_TYPE: edge_type}
        drafts = [events.Draft(record, events.KIND_EDGE_RETRACTED, payload)]
        return _append(ledger, drafts, context, lock)


def delete(
    directory: Path | str,
    record: str,
    *,
    context: Any = None,
) -> list:

    admitted, context = vault_write.admission(directory, context, environment())
    ledger = _ledger(admitted)
    with events.LedgerLock(ledger) as lock:
        _require(ledger, record)
        return _append(ledger, [events.Draft(record, events.KIND_TOMBSTONE, {})], context, lock)


def create_root(
    directory: Path | str,
    fields: Mapping[str, object],
    *,
    prefix: str,
    status: str = "open",
    context: Any = None,
) -> list:

    prefix = vault_write.prefix(directory, prefix)
    admitted, context = vault_write.admission(directory, context, environment())
    ledger = Path(admitted)
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
        return _append(ledger, drafts, context, lock)


def create_child(
    directory: Path | str,
    parent: str,
    fields: Mapping[str, object],
    *,
    status: str = "open",
    context: Any = None,
) -> list:

    admitted, context = vault_write.admission(directory, context, environment())
    ledger = _ledger(admitted)
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
        return _append(ledger, drafts, context, lock)


def migrate_fields(directory: Path | str, *, context: Any = None) -> list:

    admitted, context = vault_write.admission(directory, context, environment())
    ledger = _ledger(admitted)
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
        return _append(ledger, drafts, context, lock) if drafts else []


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


def resolve(directory: Path | str, record: str, *, context: Any = None) -> list:

    admitted, context = vault_write.admission(directory, context, environment())
    ledger = _ledger(admitted)
    with events.LedgerLock(ledger) as lock:
        state = _require(ledger, record)
        ordered = events.canonical_order(events.read_events(ledger)[0])
        keys = sorted({one["key"] for one in forks.of_record(ordered, record)})
        if not keys:
            raise TrackerCommandError(f"{record} has no unresolved conflict to resolve")
        drafts = [draft for key in keys for draft in _restated(record, state, str(key))]
        appended = _append(ledger, drafts, context, lock, repeat=True)
        if not appended:
            raise TrackerCommandError(f"resolve {record} appended nothing, so the fork stays")
        return appended


record_process = review.process.record_process
assign = holder_writes.assign
claim = holder_writes.claim
unassign = holder_writes.unassign
