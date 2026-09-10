r"""Import a foreign tracker's export into the event log, with deletion as a statement.

**This module's live input contract is the beads JSONL export format**, conventionally
`.beads/issues.jsonl`: one JSON record per line. That format is the only thing this module
reads, so every mention of it below is the contract rather than a citation — the kit itself
neither writes nor requires it (`work-tracker.md` §5, basicly-vkh0.17).

## The three §5.1 risks, and what each one is here

The format's owner demoted it to an export, so it is a second-class citizen that will drift
under this reader. That gives the import three properties it would otherwise be tempting to
discover late:

1. **The format will drift, so one bad record is a finding rather than a failed import.**
   An unparseable line, an id the commit gate would refuse, an edge pointing at something
   that is not a record id: each is reported by subject and reason and the rest of the
   export still lands. A source field this version never heard of is imported **verbatim**
   as a record field, because dropping it would lose data silently while carrying it
   forward costs nothing. The export is also **pinned**: its sha256 is recorded on the
   record it created, so a later reader can say which snapshot a record arrived from.

2. **The export is upsert-only, so absence is ambiguous and never a deletion.** Upstream
   states it "cannot infer that records absent from an export were deleted, pruned, or
   simply never exported", so neither can this. A record this source imported that the
   snapshot no longer holds is reported in :attr:`ImportReport.absent` — named, so it is
   not silently retained, and **not** tombstoned, because the snapshot cannot express that
   deletion. A caller who has confirmed the deletion out of band passes the id back as
   ``deleted``, which appends a ``tombstone`` event. A deletion is therefore a *statement*
   a caller makes, and the tombstone is a first-class event carrying the same provenance as
   everything else. It is also refused for a record the snapshot still asserts: that
   combination is a contradiction, not a deletion.

3. **A one-shot import is the only import, so a record is created once.** A record the
   ledger already holds gets no second ``created`` event; if the source's fields disagree
   with the ledger's, it is reported in :attr:`ImportReport.diverged` and **nothing is
   reconciled**. An import is not a sync, and this is where a "helpful" field patch would
   quietly make two sources of truth. The monotone parts — a new comment, a new edge, a
   status the ledger has not reached — do still land, so an import torn off at the tail
   completes on a re-run instead of wedging.

## Provenance, and why the digest is not on every event

Every event carries ``provenance: EXTRACTED`` and ``imported_from: <source name>``. §9.6's
vocabulary puts an import on the trusted side — "mechanically derived from a fact in the
repo" — so an imported edge may gate a landing, which is the whole point of importing the
dependency graph rather than re-deriving it. The vocabulary itself is §9.6's and is owned
by `provenance.py` (basicly-vkh0.13), including the promotion of an ``INFERRED`` edge; what
this module owns is which label an import writes.

The export's digest is recorded on the ``created`` event **only**, and that is a
correctness rule rather than economy. An event id is derived from its payload, so a digest
in every payload would give every comment, edge and status a different id in every export
file — and re-importing a re-serialised export would then duplicate the entire history
instead of being a replay. ``created`` is minted once per record, so it is the one place a
per-snapshot value cannot destabilise an id. The test that would have caught this imports
the same facts from a differently-serialised export and asserts nothing lands.

## The read-check-write is one critical section

Deciding what to append needs the ledger's current state, so this holds the ledger's writer
lock across its own read **and** `events.append`'s write, using the ``held_lock`` seam
§4.5 provides for exactly this. Two importers racing would otherwise both decide that a
record needs creating.

## What the fold makes of it today

``edge`` is a kind `events.py` has no handler for, so a fold counts it in
:attr:`FoldResult.delegated_kinds` and folds no edge state. That is the delegation
working as specified — this module is the newer writer — and basicly-vkh0.13 adds the
handler. The totals count an edge event either way, so an old reader reports no false
disagreement.

## What this module may not do

Kit rules (§4): **no basicly**, standard library only, no network, no subprocess. It reads
the export and the ledger and takes the clock, the actor and the redactor as arguments. It
must stay parseable by an interpreter older than this repo's 3.14 floor: no syntax newer
than 3.9, and one exception class per handler
(`.basicly/core/kit/README.md`).
"""

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

# --- errors -------------------------------------------------------------------


class SnapshotError(ValueError):
    """A source snapshot, or a label for one, that this module refuses whole."""


# --- the sibling event log -----------------------------------------------------

_HERE = Path(__file__).resolve().parent
_EVENTS_MODULE_NAME = "basicly_tracker_kit_events"


def _load_events() -> ModuleType:
    """Load ``events.py`` from beside this file, without touching ``sys.path``.

    The same by-path load `events.py` uses for `ids.py`, and for the same reason: the kit
    is a set of sibling files rather than a package, and a library loaded into somebody
    else's process may not claim the bare name ``events``. It is annotated
    :class:`~types.ModuleType` rather than ``object`` so the many calls through it type
    check without a suppression on each one.
    """
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

# The id module the event log already loaded. Taken from there rather than loaded again, so
# there is one `ids` in the process and an `IdError` raised inside `append` is the same
# class this module would catch.
ids = events.ids

# --- the vocabulary an import writes ------------------------------------------

# §9.6's trusted label: an import is mechanically derived from a fact in the repo, so an
# imported edge may gate a landing. `provenance.py` (basicly-vkh0.13) owns the vocabulary;
# this names the one entry an import uses.
EXTRACTED = "EXTRACTED"

PROVENANCE_KEY = "provenance"
SOURCE_KEY = "imported_from"
DIGEST_KEY = "import_digest"

# Reserved on a record's fields. A source record carrying one of these is refused rather
# than imported: it would overwrite the provenance of the very event recording it.
RESERVED_KEYS = frozenset({PROVENANCE_KEY, SOURCE_KEY, DIGEST_KEY})

# A dependency edge, spelled once in `events.py`. No fold handler until basicly-vkh0.13's,
# which is additive by construction — see the module docstring.
KIND_EDGE = events.KIND_EDGE

EDGE_FROM = "from"
EDGE_TO = "to"
EDGE_TYPE = "type"

# Source fields that become events of their own rather than record fields. Everything else
# on a source record — including a field this version has never heard of — is imported
# verbatim onto the `created` event.
ID_FIELD = "id"
STATUS_FIELD = "status"
COMMENTS_FIELD = "comments"
DEPENDENCIES_FIELD = "dependencies"
STRUCTURAL_FIELDS = frozenset({ID_FIELD, STATUS_FIELD, COMMENTS_FIELD, DEPENDENCIES_FIELD})

# The source's own attribution for a comment or an edge, kept under our own names so it can
# never be mistaken for the ledger's actor or the event's own timestamp.
SOURCE_ID_KEY = "source_id"
ASSERTED_BY_KEY = "asserted_by"
ASSERTED_AT_KEY = "asserted_at"

# Why a tombstone was written, when the caller does not say. Free text under a capped key,
# so a caller's longer reason is truncated rather than refused.
DETAIL_KEY = "detail"
DEFAULT_DELETION_DETAIL = "absent from the source snapshot and confirmed deleted by the caller"


# --- the parsed snapshot -------------------------------------------------------


@dataclass(frozen=True)
class Rejection:
    """One thing the source said that could not become an event, and why.

    Attributes:
        subject: What was refused — a record id, ``"line 12"``, or a part of a record such
            as ``"basicly-aa11 edge -> basicly-bb22"``.
        reason: Why, in the terms a reader can act on.
    """

    subject: str
    reason: str


@dataclass(frozen=True)
class Snapshot:
    """One parsed export, pinned by digest.

    Attributes:
        name: The label written into every event as ``imported_from``. A label, never a
            path — see :func:`validate_source_name`.
        digest: sha256 of the export's whole text, recorded on each ``created`` event.
        records: The record objects, in file order.
        unreadable: Lines that were not a JSON object, by line number.
    """

    name: str
    digest: str
    records: tuple[Mapping[str, object], ...]
    unreadable: tuple[Rejection, ...]


def validate_source_name(name: str) -> str:
    """Return *name* unchanged, or raise :class:`SnapshotError` naming what is wrong.

    The name is written into **every** event this module appends and the ledger is
    committed, so a machine path here would be committed too — the defect basicly-vkh0.5
    already paid for. Both path flavours are asked rather than the host's: ``Path`` is
    whichever platform is running, so a rule checked through it is only ever checked on one
    of the three.

    Raises:
        SnapshotError: *name* is empty, padded, home-relative, absolute in either flavour,
            or carries a Windows drive or UNC share.
    """
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
    """Parse an export's *text* into a :class:`Snapshot` labelled *name*.

    A line that is not a JSON object is reported, never tolerated — the opposite of the
    ledger's torn-trailing-line rule, and deliberately. A torn line in the ledger is our
    own crash and the one case where a lost line is expected; a truncated line in somebody
    else's export is format drift, which §5.1 says to expect and to *see*.

    Raises:
        SnapshotError: *name* is not a portable label.
    """
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
    """Read and parse the export at *path*, defaulting *name* to the file's base name.

    The text is decoded with universal newlines, so a CRLF checkout digests to the same pin
    as an LF one — the export is not ours to declare ``-text`` in `.gitattributes`, and a
    digest that changed with the checkout would make the pin useless on Windows.

    Raises:
        SnapshotError: *name* is not a portable label.
    """
    file_path = Path(path)
    return parse_snapshot(
        file_path.read_text(encoding="utf-8"),
        name=file_path.name if name is None else name,
    )


# --- the import ---------------------------------------------------------------


@dataclass
class ImportReport:
    """What an import did, and what it declined to guess at.

    Attributes:
        events: The events that landed, in write order. Empty on a replay.
        imported: Records whose ``created`` event landed in this call.
        diverged: Records the ledger already holds whose source fields disagree with the
            ledger's. Reported, never reconciled: an import is not a sync (§5.1).
        absent: Records this source imported that the snapshot no longer holds. **Not
            deletions** — an upsert-only export cannot express one, so absence is ambiguous
            by construction. A caller who has confirmed the deletion passes the id back as
            ``deleted``.
        tombstoned: Records whose ``tombstone`` event landed in this call.
        rejected: Parts of the source that could not become events.
        unreadable: Lines the snapshot could not parse, carried from :class:`Snapshot`.
    """

    events: list[Any] = field(default_factory=list)
    imported: list[str] = field(default_factory=list)
    diverged: list[str] = field(default_factory=list)
    absent: list[str] = field(default_factory=list)
    tombstoned: list[str] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    unreadable: list[Rejection] = field(default_factory=list)


@dataclass(frozen=True)
class _Held:
    """What the ledger already holds about one record.

    Attributes:
        created: The payload of its ``created`` event, or ``None`` if it has none.
        status: Its folded status, or ``None``.
        tombstoned: Whether a tombstone has already landed on it, so it is not reported
            absent a second time.
        status_counts: How many times each status value has already been recorded on it,
            which is what decides a re-recording's ``generation`` (§9.4's trap).
    """

    created: Mapping[str, object] | None = None
    status: str | None = None
    tombstoned: bool = False
    status_counts: Mapping[str, int] = field(default_factory=dict)


@dataclass
class _Plan:
    """The drafts one source record becomes, plus what it cost to get there."""

    drafts: list[Any] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    diverged: bool = False


def _held_records(existing: Iterable[Any], folded: Any) -> dict[str, _Held]:
    """What the ledger holds, per record, in the shape :func:`_plan_record` reads."""
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
    """*payload* without the provenance this module added, for comparing two imports.

    The digest is one of the keys dropped, and that is the point: two exports of the same
    facts differ in their digest, and comparing it would report every record as diverged.
    """
    return {key: value for key, value in payload.items() if key not in RESERVED_KEYS}


def _comment_drafts(record: str, raw: Mapping[str, object], provenance: Mapping[str, object]):
    """Drafts for one record's comments, and the ones refused.

    The source's comment id is carried, which is what keeps two identical texts two
    events: without it they would be the same fact recorded twice and the second would be
    swallowed as a replay.
    """
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
    """Drafts for one record's dependency edges, and the ones refused.

    The event is recorded on the **dependent** record, which is the item the edge is about
    and so the item whose sequence it takes. A target that is not a record id is refused
    rather than written: an edge into nothing would gate a landing on a record that cannot
    exist.
    """
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
    """Everything one source record contributes to an import.

    *prepare* renders a payload the way `append` will store it — redacted and capped — and
    is used for two things: it refuses a shape the ledger cannot hold (a capped key holding
    a container) so one bad record is a rejection rather than a failed batch, and it makes
    the divergence comparison compare like with like. A raw comparison would call a record
    diverged whenever the redactor had changed one of its values.
    """
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
        # Reported, and no draft: a second `created` event would fold over the first and
        # make the import a sync (§5.1). The record's other parts still import.
        plan.diverged = True

    status = raw.get(STATUS_FIELD)
    if not isinstance(status, str) or not status:
        plan.rejections.append(
            Rejection(f"{record} status", f"not a non-empty string, got {status!r}")
        )
    elif status != held.status:
        payload = dict(provenance)
        payload[STATUS_FIELD] = status
        # A status the record has held before — `closed -> open -> closed` — repeats a fact
        # already recorded, so its content-derived id is the first one's and the event
        # would be swallowed as a replay. `generation` is what §9.4 has for exactly this.
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
    """Tombstone drafts for the deletions a caller **states**, and the ones refused.

    The export cannot express a deletion, so this is the only path to a tombstone and it
    takes an explicit list. Two refusals, both contradictions rather than absences: a
    record the ledger never held has nothing to tombstone, and a record the snapshot still
    asserts is not deleted — accepting that would let a caller delete a live record while
    calling it an import.
    """
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
) -> ImportReport:
    """Import *snapshot* into the ledger in *directory* and report what happened.

    Every event written carries ``provenance: EXTRACTED`` and ``imported_from:
    snapshot.name``; each ``created`` event also carries the export's digest. A record the
    ledger already holds is not created again — see :attr:`ImportReport.diverged` — and a
    record the snapshot omits is reported in :attr:`ImportReport.absent` rather than
    deleted, because an upsert-only export cannot express a deletion.

    Args:
        directory: The ledger directory. Created if it does not exist.
        snapshot: The parsed export, from :func:`read_snapshot` or :func:`parse_snapshot`.
        deleted: Record ids the caller **states** are deleted at the source. Each becomes a
            ``tombstone`` event. Refused for a record the snapshot still asserts.
        detail: Free text recorded on each tombstone, saying why it was written.
        actor: The lease holder recorded on every event written.
        clock: Wall clock passed through to `append`; recorded and read by nothing.
        redact: Applied to every string before it is stored, and to the copy the
            divergence comparison is made against.
        max_text_bytes: The per-field cap passed through to `append`.
        held_lock: An already-held ledger lock, for a caller whose critical section is
            wider than one import. When ``None`` one is taken for the read and the write.
        lock_timeout_s: How long to wait for the lock when taking one here.

    Raises:
        LockUnavailableError: from the event log — the ledger's writer lock could not be
            taken. Retryable.
    """
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
            """One payload as `append` will store it, for the shape check and the compare."""
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
        # Derived from what landed rather than from what was planned: a draft whose id is
        # already in the ledger is skipped as a replay, and a report that claimed it anyway
        # would be the carried-total defect in a new place.
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
