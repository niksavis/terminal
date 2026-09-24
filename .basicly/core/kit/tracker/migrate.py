from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import ModuleType
from typing import Any


class SnapshotError(ValueError):
    pass


_HERE = Path(__file__).resolve().parent
_EVENTS_MODULE_NAME = "basicly_tracker_kit_events"


def _load_events() -> ModuleType:

    cached = sys.modules.get(_EVENTS_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_EVENTS_MODULE_NAME, _HERE / "events.py")
    if spec is None or spec.loader is None:
        raise SnapshotError("the tracker kit's events.py is missing from beside migrate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_EVENTS_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


events = _load_events()

ids = events.ids


EXTRACTED = "EXTRACTED"

PROVENANCE_KEY = "provenance"
SOURCE_KEY = "imported_from"
DIGEST_KEY = "import_digest"

RESERVED_KEYS = frozenset({PROVENANCE_KEY, SOURCE_KEY, DIGEST_KEY})

KIND_EDGE = events.KIND_EDGE

EDGE_FROM = "from"
EDGE_TO = "to"
EDGE_TYPE = "type"

ID_FIELD = "id"
STATUS_FIELD = "status"
COMMENTS_FIELD = "comments"
DEPENDENCIES_FIELD = "dependencies"
STRUCTURAL_FIELDS = frozenset({ID_FIELD, STATUS_FIELD, COMMENTS_FIELD, DEPENDENCIES_FIELD})

SOURCE_ID_KEY = "source_id"
ASSERTED_BY_KEY = "asserted_by"
ASSERTED_AT_KEY = "asserted_at"

DETAIL_KEY = "detail"
DEFAULT_DELETION_DETAIL = "absent from the source snapshot and confirmed deleted by the caller"


@dataclass(frozen=True)
class Rejection:
    subject: str
    reason: str


@dataclass(frozen=True)
class Snapshot:
    name: str
    digest: str
    records: tuple[Mapping[str, object], ...]
    unreadable: tuple[Rejection, ...]


def validate_source_name(name: str) -> str:

    if not name or name != name.strip():
        raise SnapshotError(f"source name {name!r} must be a non-empty label with no padding")
    if name.startswith("~"):
        raise SnapshotError(
            f"source name {name!r} is home-relative: it names one machine's home directory"
        )
    if PurePosixPath(name).is_absolute() or PureWindowsPath(name).is_absolute():
        raise SnapshotError(
            f"source name {name!r} is an absolute path: it is recorded on every imported "
            f"event and the ledger is committed, so it must be a portable label"
        )
    if PureWindowsPath(name).drive:
        raise SnapshotError(
            f"source name {name!r} carries a Windows drive or share: it must be a portable label"
        )
    return name


def parse_snapshot(text: str, *, name: str) -> Snapshot:

    validate_source_name(name)
    records: list[Mapping[str, object]] = []
    unreadable: list[Rejection] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError as exc:
            unreadable.append(Rejection(f"line {number}", f"not JSON: {exc}"))
            continue
        if not isinstance(raw, dict):
            unreadable.append(
                Rejection(f"line {number}", f"not a JSON object: {type(raw).__name__}")
            )
            continue
        records.append(raw)
    return Snapshot(
        name=name,
        digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        records=tuple(records),
        unreadable=tuple(unreadable),
    )


def read_snapshot(path: Path | str, *, name: str | None = None) -> Snapshot:

    file_path = Path(path)
    return parse_snapshot(
        file_path.read_text(encoding="utf-8"),
        name=file_path.name if name is None else name,
    )


@dataclass
class ImportReport:
    events: list[Any] = field(default_factory=list)
    imported: list[str] = field(default_factory=list)
    diverged: list[str] = field(default_factory=list)
    absent: list[str] = field(default_factory=list)
    tombstoned: list[str] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    unreadable: list[Rejection] = field(default_factory=list)


@dataclass(frozen=True)
class _Held:
    created: Mapping[str, object] | None = None
    status: str | None = None
    tombstoned: bool = False
    status_counts: Mapping[str, int] = field(default_factory=dict)


@dataclass
class _Plan:
    drafts: list[Any] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    diverged: bool = False


def _held_records(existing: Iterable[Any], folded: Any) -> dict[str, _Held]:
    created: dict[str, Mapping[str, object]] = {}
    counts: dict[str, dict[str, int]] = {}
    for event in existing:
        if event.kind == events.KIND_CREATED:
            created.setdefault(event.record, event.payload)
        elif event.kind == events.KIND_STATUS:
            value = event.payload.get(STATUS_FIELD)
            if isinstance(value, str):
                per_record = counts.setdefault(event.record, {})
                per_record[value] = per_record.get(value, 0) + 1
    return {
        record: _Held(
            created=created.get(record),
            status=state.status,
            tombstoned=state.tombstoned,
            status_counts=counts.get(record, {}),
        )
        for record, state in folded.records.items()
    }


def _own_fields(payload: Mapping[str, object]) -> dict[str, object]:

    return {key: value for key, value in payload.items() if key not in RESERVED_KEYS}


def _comment_drafts(record: str, raw: Mapping[str, object], provenance: Mapping[str, object]):

    drafts: list[Any] = []
    rejections: list[Rejection] = []
    found = raw.get(COMMENTS_FIELD)
    if found is None:
        return drafts, rejections
    if not isinstance(found, list):
        rejections.append(Rejection(f"{record} comments", f"not a list: {type(found).__name__}"))
        return drafts, rejections
    for index, comment in enumerate(found, start=1):
        subject = f"{record} comment {index}"
        if not isinstance(comment, dict):
            rejections.append(Rejection(subject, f"not an object: {type(comment).__name__}"))
            continue
        text = comment.get("text")
        if not isinstance(text, str):
            rejections.append(Rejection(subject, f"has no string text, got {text!r}"))
            continue
        payload = dict(provenance)
        payload["text"] = text
        for source_key, payload_key in (
            ("id", SOURCE_ID_KEY),
            ("author", ASSERTED_BY_KEY),
            ("created_at", ASSERTED_AT_KEY),
        ):
            value = comment.get(source_key)
            if value is not None:
                payload[payload_key] = value
        drafts.append(events.Draft(record, events.KIND_COMMENT, payload))
    return drafts, rejections


def _edge_drafts(record: str, raw: Mapping[str, object], provenance: Mapping[str, object]):

    drafts: list[Any] = []
    rejections: list[Rejection] = []
    found = raw.get(DEPENDENCIES_FIELD)
    if found is None:
        return drafts, rejections
    if not isinstance(found, list):
        rejections.append(
            Rejection(f"{record} dependencies", f"not a list: {type(found).__name__}")
        )
        return drafts, rejections
    for index, edge in enumerate(found, start=1):
        subject = f"{record} edge {index}"
        if not isinstance(edge, dict):
            rejections.append(Rejection(subject, f"not an object: {type(edge).__name__}"))
            continue
        target = edge.get("depends_on_id")
        edge_type = edge.get("type")
        holder = edge.get("issue_id")
        if not isinstance(target, str) or not ids.is_record_id(target):
            rejections.append(Rejection(subject, f"depends_on_id {target!r} is not a record id"))
            continue
        if not isinstance(edge_type, str) or not edge_type:
            rejections.append(Rejection(subject, f"type {edge_type!r} is not a non-empty string"))
            continue
        if isinstance(holder, str) and holder != record:
            rejections.append(
                Rejection(subject, f"issue_id {holder!r} contradicts the record it is listed on")
            )
            continue
        payload = dict(provenance)
        payload[EDGE_FROM] = record
        payload[EDGE_TO] = target
        payload[EDGE_TYPE] = edge_type
        for source_key, payload_key in (
            ("created_by", ASSERTED_BY_KEY),
            ("created_at", ASSERTED_AT_KEY),
        ):
            value = edge.get(source_key)
            if value is not None:
                payload[payload_key] = value
        drafts.append(events.Draft(record, KIND_EDGE, payload))
    return drafts, rejections


def _plan_record(
    record: str,
    raw: Mapping[str, object],
    snapshot: Snapshot,
    held: _Held,
    prepare: Any,
) -> _Plan:

    plan = _Plan()
    provenance = {PROVENANCE_KEY: EXTRACTED, SOURCE_KEY: snapshot.name}
    fields = {key: value for key, value in raw.items() if key not in STRUCTURAL_FIELDS}
    try:
        prepared = prepare(fields)
    except events.InvalidEventError as exc:
        plan.rejections.append(Rejection(record, f"the ledger cannot hold its fields: {exc}"))
        return plan

    if held.created is None:
        created = dict(fields)
        created.update(provenance)
        created[DIGEST_KEY] = snapshot.digest
        plan.drafts.append(events.Draft(record, events.KIND_CREATED, created))
    elif _own_fields(held.created) != prepared:
        plan.diverged = True

    status = raw.get(STATUS_FIELD)
    if not isinstance(status, str) or not status:
        plan.rejections.append(
            Rejection(f"{record} status", f"not a non-empty string, got {status!r}")
        )
    elif status != held.status:
        payload = dict(provenance)
        payload[STATUS_FIELD] = status
        generation = held.status_counts.get(status, 0) + 1
        plan.drafts.append(events.Draft(record, events.KIND_STATUS, payload, generation=generation))

    for builder in (_comment_drafts, _edge_drafts):
        drafts, rejections = builder(record, raw, provenance)
        plan.drafts.extend(drafts)
        plan.rejections.extend(rejections)
    return plan


def _deletion_drafts(
    deleted: Iterable[str],
    snapshot: Snapshot,
    asserted: set[str],
    held: Mapping[str, _Held],
    detail: str,
):

    drafts: list[Any] = []
    rejections: list[Rejection] = []
    for record in deleted:
        if not isinstance(record, str) or not ids.is_record_id(record):
            rejections.append(Rejection(repr(record), "not a record id, so nothing to tombstone"))
            continue
        if record not in held:
            rejections.append(
                Rejection(record, "the ledger holds no such record, so nothing to tombstone")
            )
            continue
        if record in asserted:
            rejections.append(
                Rejection(record, "the snapshot still asserts this record: not a deletion")
            )
            continue
        payload = {
            PROVENANCE_KEY: EXTRACTED,
            SOURCE_KEY: snapshot.name,
            DETAIL_KEY: detail,
        }
        drafts.append(events.Draft(record, events.KIND_TOMBSTONE, payload))
    return drafts, rejections


def import_snapshot(  # noqa: PLR0913 — every keyword past the snapshot is an injected seam
    directory: Path | str,
    snapshot: Snapshot,
    *,
    deleted: Iterable[str] = (),
    detail: str = DEFAULT_DELETION_DETAIL,
    actor: str = "",
    clock: Any = None,
    redact: Any = None,
    max_text_bytes: int = events.MAX_TEXT_BYTES,
    held_lock: Any = None,
    lock_timeout_s: float = events.DEFAULT_LOCK_TIMEOUT_S,
    dry_run: bool = False,
) -> ImportReport:

    ledger = Path(directory)
    acquired = held_lock is None
    lock = events.LedgerLock(ledger, timeout_s=lock_timeout_s) if acquired else held_lock
    if acquired:
        lock.acquire()
    try:
        existing, _ = events.read_events(ledger)
        held = _held_records(existing, events.fold(existing))
        report = ImportReport(unreadable=list(snapshot.unreadable))
        drafts: list[Any] = []
        asserted: set[str] = set()

        def prepare(payload: Mapping[str, object]) -> dict[str, object]:
            return events.prepare_payload(payload, redact=redact, max_text_bytes=max_text_bytes)

        for raw in snapshot.records:
            record = raw.get(ID_FIELD)
            if not isinstance(record, str) or not ids.is_record_id(record):
                report.rejected.append(Rejection(repr(record), "not a record id"))
                continue
            if record in asserted:
                report.rejected.append(
                    Rejection(record, "the snapshot holds more than one record under this id")
                )
                continue
            asserted.add(record)
            reserved = sorted(RESERVED_KEYS.intersection(raw))
            if reserved:
                report.rejected.append(
                    Rejection(
                        record,
                        f"carries reserved provenance field(s) {', '.join(reserved)}: importing "
                        f"it would overwrite the provenance of the event recording it",
                    )
                )
                continue
            plan = _plan_record(record, raw, snapshot, held.get(record, _Held()), prepare)
            drafts.extend(plan.drafts)
            report.rejected.extend(plan.rejections)
            if plan.diverged:
                report.diverged.append(record)

        report.absent = sorted(
            record
            for record, state in held.items()
            if record not in asserted
            and state.created is not None
            and state.created.get(SOURCE_KEY) == snapshot.name
            and not state.tombstoned
        )
        tombstones, refused = _deletion_drafts(deleted, snapshot, asserted, held, detail)
        drafts.extend(tombstones)
        report.rejected.extend(refused)

        if dry_run:
            report.imported = sorted(
                draft.record for draft in drafts if draft.kind == events.KIND_CREATED
            )
            report.tombstoned = sorted(
                draft.record for draft in drafts if draft.kind == events.KIND_TOMBSTONE
            )
            return report

        minted = events.append(
            ledger,
            drafts,
            actor=actor,
            clock=clock,
            redact=redact,
            max_text_bytes=max_text_bytes,
            held_lock=lock,
        )
        report.events = minted
        report.imported = sorted(
            event.record for event in minted if event.kind == events.KIND_CREATED
        )
        report.tombstoned = sorted(
            event.record for event in minted if event.kind == events.KIND_TOMBSTONE
        )
        return report
    finally:
        if acquired:
            lock.release()


def import_report(
    directory: Path | str,
    export: Path | str,
    *,
    source: str = "",
    redact: Any = None,
    dry_run: bool = False,
) -> dict[str, object]:

    named = source or Path(export).name
    read = read_snapshot(export, name=named)
    report = import_snapshot(directory, read, redact=redact, dry_run=dry_run)
    return {
        "source": named,
        "dry_run": dry_run,
        "imported": report.imported,
        "diverged": report.diverged,
        "absent": report.absent,
        "tombstoned": report.tombstoned,
        "rejected": [
            {"subject": one.subject, "reason": one.reason}
            for one in (*report.rejected, *report.unreadable)
        ],
    }
