r"""The derived record snapshot: a fold you can keep, and prove stale without folding.

The log is the truth; this file is a **projection of it that anybody may delete**
(§4 in `SPEC.md`, basicly-vkh0.14). Everything here follows from that one
sentence, including the parts that look like extra work.

## Derived means gitignored, not committed

Calling a file derived and then committing it recreates the dual-store failure the event
log exists to escape: two branches each rebuild it, any record changed on both sides is a
same-line conflict git cannot union-merge, and until somebody rebuilds, the repo holds two
sources of truth that disagree. So `snapshot.jsonl` and every `checkpoint-*.jsonl` are
**local artifacts**. :data:`DERIVED_PATTERNS` is the set, and it is the kit's one deployment
requirement here — the ledger directory's ignore rules must cover those two patterns, the
way `events-*.jsonl` must be declared ``-text`` for `events.py`. Neither pattern matches a
log name, which is asserted rather than eyeballed: an ignore rule that swallowed the log
would delete the truth to save a cache.

## The header is the staleness detector, and it costs a scan rather than a fold

**The first line carries the ledger's tip event id and the number of events folded.** Any
reader can therefore date the snapshot against the log by *scanning* — counting newlines
and decoding exactly one line — instead of folding, which is the whole cost being avoided.
Without it, a crash between the fold and the rename serves stale state forever with nothing
to notice.

Two decisions inside that, both easy to get backwards:

- **The id is the log's tip — the last line of the last file — not the canonical maximum.**
  Canonical order sorts by ``(record, seq, id)`` (§4.1), so its maximum is the highest
  *record id*'s last event, which no cheap read of the log can find. The tip is what a tail
  read gives, so the tip is what is recorded.
- **The scan is taken before the fold, never after.** If the log grows in between, a
  scan-first header under-reports and the snapshot reads as stale; a scan-second header
  would claim to have folded a line it never saw and read as **fresh**. The invariant is
  one-directional and this is where it is won: a cheap check may say stale when it is
  fresh, and may never say fresh when it is stale.

:func:`staleness` compares the header against a fresh scan on two axes — the line count and
the tip id — and reports *why*, because a hook that only says "rebuilt" teaches nobody
anything. The line count rather than the event count is the comparator that survives a
quarantined line: a log with interior garbage would otherwise read as permanently stale and
rebuild on every single read.

## Regeneration: lazily on a stale read, and by a hook

:func:`load` is the reader's entry point — it returns the snapshot when the header says it
is current and regenerates first when it does not. :func:`main` is the same thing for a
``post-merge``/``post-checkout`` hook, which is the case laziness cannot cover: a checkout
that changes the log leaves every reader's next read paying for the rebuild, and a merge
that brings in another branch's events is exactly when the snapshot is most wrong::

    python3 .basicly/core/kit/tracker/snapshot.py <ledger-directory>

It writes nothing when the ledger directory does not exist, so wiring the hook into a
repository that has no tracker yet is inert rather than an error.

## Rotation, and the checkpoint that bounds the steady state

Rotation is by period — ``events-2027.jsonl`` — and rotated files are **archived, never
pruned**, because folding the whole history is a requirement (§4.3 requirement 6). Rotation
therefore deletes nothing and moves nothing: it writes one new empty file whose name sorts
last, and `events.append_target` starts using it because that is what sorting last means.
The period is an **argument**, never read from a clock: choosing it here would put a
wall-clock branch (*which year is it*) on the write path, which §9.5 forbids.

Rotation alone does not make steady state cheaper — the same events are parsed however many
files hold them — so each boundary also publishes a **checkpoint**: the full fold as of that
boundary, in this same format, under a name that sorts with its period. Steady state
(:func:`fold_resumed`) is then *one checkpoint plus the files after it*, while the
full-history fold (:func:`fold_all`) stays available and is what `fsck` and `rebuild` use.
§4.6's bound — "current file, then one checkpoint", never "the whole history" — is a
requirement on the checkpoint carrying **every** item's totals, including an item idle since
before the boundary, and that is asserted rather than assumed.

The one property the resumed fold does not have: a seeded item's already-claimed sequence
numbers are not in the checkpoint, so a fork straddling the boundary is invisible to it and
only the full-history fold reports one. A reader that must be *right* about a fork folds
everything; that is the same rule §4.6 states for the carried totals.

## Read by contract, not by convention

Nothing here spells ``events-`` or ``.jsonl`` a second time: the rotation name and the
checkpoint name are **derived from `events.LOG_GLOB`**, so a narrowed glob does not quietly
drop an archive from the fold — it renames the file rotation creates, and the tests fail from
both directions.

## What this module may not do

Kit rules (§4): **no basicly**, standard library only, no network, no subprocess. It reads
and writes its own ledger directory and takes everything else — the period, the lock — as an
argument, and it must stay parseable by an interpreter older than this repo's 3.14 floor: no
syntax newer than 3.9, and one exception class per handler
(`.basicly/core/kit/README.md`).

Two things it deliberately does **not** do. It never repairs a derivative: a snapshot or a
checkpoint that cannot be parsed is *replaced from the log*, because a repaired cache is a
second source of truth wearing a green tick. And it never edits or truncates a log — the
`fsck`/`rebuild` commands that report on one are basicly-vkh0.15's, and they consume
:func:`fold_all` and :func:`derived_paths` rather than reimplementing either.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- the sibling event log ----------------------------------------------------

_HERE = Path(__file__).resolve().parent
_EVENTS_MODULE_NAME = "basicly_tracker_kit_events"


def _load_events() -> Any:
    """Load ``events.py`` from beside this file, without touching ``sys.path``.

    The kit is a set of sibling files rather than a package, so a relative import is not
    available; loading by path under a qualified name mutates nothing a consumer owns.
    The cache lookup is what makes the module object **shared** — two loads would mint two
    ``Event`` classes, and a dataclass compares unequal across them, so a snapshot folded
    through one copy would never match a fold taken through the other.

    Raises:
        ImportError: ``events.py`` is not beside this file. Deliberately not the ledger's
            own error family: that family is defined in the module being loaded.
    """
    cached = sys.modules.get(_EVENTS_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_EVENTS_MODULE_NAME, _HERE / "events.py")
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's events.py is missing from beside snapshot.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_EVENTS_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


events = _load_events()

# --- the derived files' shape -------------------------------------------------

# Derived from the log glob rather than spelled again, so `events-*.jsonl` stays one fact:
# rotation's file name and the checkpoint's suffix both move with it. `partition` rather
# than `split` because a glob with no `*` must not raise at import time.
_LOG_PREFIX, _, _LOG_SUFFIX = events.LOG_GLOB.partition("*")

SNAPSHOT_NAME = "snapshot" + _LOG_SUFFIX
CHECKPOINT_PREFIX = "checkpoint-"
CHECKPOINT_GLOB = CHECKPOINT_PREFIX + "*" + _LOG_SUFFIX

# What the ledger directory's ignore rules must cover, and the set `rebuild` may delete.
# Neither pattern may match a log name — see `derived_paths`.
DERIVED_PATTERNS = (SNAPSHOT_NAME, CHECKPOINT_GLOB)

# The format version of a snapshot or a checkpoint. A derived file's forward-compatibility
# answer is **not** the log's tolerant one: an unknown field on an event line is preserved
# because the log is irreplaceable, while a snapshot from a newer writer is simply refused
# and rebuilt from the log, which costs one fold and cannot serve a field it misread.
SNAPSHOT_VERSION = 1

# A rotation period. Fixed-width leading digits so lexicographic order **is** period order,
# which is what makes `events-2027.jsonl` sort after `events-2026.jsonl` and the zero-padded
# initial name sort before both; an optional lowercase tail allows a finer period (`2026q1`).
# The order is checked against the current file as well, so this pattern is a guard rather
# than the guarantee.
PERIOD_PATTERN = re.compile(r"^[0-9]{4,}[a-z0-9]*$")

# The scan reads bytes and counts newlines. 64 KiB is one ordinary filesystem read-ahead
# window; the number is not load-bearing, the streaming is — a ledger archive may be large
# and staleness must not cost a full read into memory.
SCAN_CHUNK_BYTES = 65536


class SnapshotError(events.LedgerError):
    """A derived file this module refuses to believe, or a rotation it refuses to perform.

    In the ledger's error family so a caller can catch it beside `LedgerError`. A caller
    that hits one on a *read* has a corrupt derivative and should rebuild; every writer here
    already does.
    """


# --- the header ---------------------------------------------------------------


@dataclass(frozen=True)
class Header:
    """The first line of a snapshot or a checkpoint: what it folded.

    Attributes:
        last_event_id: The id on the **last line of the last log file** at scan time — the
            ledger's tip. ``None`` for a ledger with no parseable event.
        event_count: Events the fold consumed, including any a checkpoint stood in for.
            Duplicated ids are counted as read, so this is comparable with a line count.
        log_lines: Non-blank lines the scan counted across every log file. The staleness
            comparator, because unlike ``event_count`` it is unchanged by a quarantined
            line.
        version: :data:`SNAPSHOT_VERSION`. A higher one is refused, never guessed at.
    """

    last_event_id: str | None = None
    event_count: int = 0
    log_lines: int = 0
    version: int = SNAPSHOT_VERSION

    def as_dict(self) -> dict[str, object]:
        """The JSON form written as the file's first line."""
        return {
            "last_event_id": self.last_event_id,
            "event_count": self.event_count,
            "log_lines": self.log_lines,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Header:
        """Read the header back, refusing anything that would misdate the snapshot.

        Raises:
            SnapshotError: a count is not a non-negative integer, the tip is not a string or
                null, the version is missing, or the version is newer than this reader
                understands. A missing version is refused rather than assumed to be this
                one: every header this format has ever written carries it, so a first line
                without one is some other file — and there is no first version to be
                backwards-compatible with.
        """
        version = raw.get("version", 0)
        if not _is_int(version):
            raise SnapshotError(f"header version must be an integer, got {version!r}")
        if int(version) < 1:  # type: ignore[arg-type]
            raise SnapshotError("the first line carries no snapshot format version")
        if int(version) > SNAPSHOT_VERSION:  # type: ignore[arg-type]
            raise SnapshotError(
                f"snapshot format version {version} is newer than {SNAPSHOT_VERSION}: "
                f"refused rather than half-read, and rebuilt from the log instead"
            )
        counts = {}
        for name in ("event_count", "log_lines"):
            value = raw.get(name, 0)
            if not _is_int(value) or int(value) < 0:  # type: ignore[arg-type]
                raise SnapshotError(f"header {name} must be a non-negative integer, got {value!r}")
            counts[name] = int(value)  # type: ignore[arg-type]
        tip = raw.get("last_event_id")
        if tip is not None and not isinstance(tip, str):
            raise SnapshotError(f"header last_event_id must be a string or null, got {tip!r}")
        return cls(last_event_id=tip, version=int(version), **counts)  # type: ignore[arg-type]


# --- the snapshot -------------------------------------------------------------


@dataclass(frozen=True)
class Snapshot:
    """A folded ledger plus the header that says which events it folded.

    A checkpoint is this same shape under a different name: it is a snapshot taken at a
    rotation boundary, which is why one serializer serves both.

    Attributes:
        header: The staleness header, written first.
        records: Record id to ``events.RecordState``, written one per line in id order.
    """

    header: Header = field(default_factory=Header)
    records: dict[str, Any] = field(default_factory=dict)


def record_to_dict(state: Any) -> dict[str, object]:
    """One folded record as its JSON line.

    Every field of ``events.RecordState`` is written, ``max_seq`` included: a reader
    resuming from a checkpoint needs the item's sequence high-water mark, and a snapshot
    that dropped it would resume folding an item as if it had no history. The same rule is
    why the typed machine state is here: a resumed fold that dropped `checkpoints` would
    read an approved item as never approved (basicly-vkh0.30).
    """
    return {
        "record": state.record,
        "status": state.status,
        "fields": dict(state.fields),
        "comments": list(state.comments),
        "checkpoints": dict(state.checkpoints),
        "artifacts": dict(state.artifacts),
        "tombstoned": state.tombstoned,
        "totals": state.totals.as_dict(),
        "max_seq": state.max_seq,
    }


def record_from_dict(raw: Mapping[str, object]) -> Any:
    """One folded record, read back as an ``events.RecordState``.

    A file written before the typed machine kinds landed carries no ``checkpoints`` and no
    ``artifacts``, and reads back empty rather than refused: no event of either kind existed
    to fold then, so empty is the state it holds, not a default standing in for one.

    Raises:
        SnapshotError: any field is missing or of the wrong type. Refused rather than
            defaulted: a snapshot that quietly read a missing status as ``None`` would
            reopen a done record, and the file is regenerable, so there is no reason to
            salvage it.
    """
    record = raw.get("record")
    if not isinstance(record, str):
        raise SnapshotError(f"record must be a string, got {record!r}")
    status = raw.get("status")
    if status is not None and not isinstance(status, str):
        raise SnapshotError(f"{record}: status must be a string or null, got {status!r}")
    fields = raw.get("fields", {})
    if not isinstance(fields, dict):
        raise SnapshotError(f"{record}: fields must be an object, got {type(fields).__name__}")
    comments = raw.get("comments", [])
    if not isinstance(comments, list) or not all(isinstance(item, str) for item in comments):
        raise SnapshotError(f"{record}: comments must be a list of strings, got {comments!r}")
    checkpoints = raw.get("checkpoints", {})
    if not isinstance(checkpoints, dict) or not all(
        isinstance(approver, str) for approver in checkpoints.values()
    ):
        raise SnapshotError(f"{record}: checkpoints map a name to an approver, got {checkpoints!r}")
    artifacts = raw.get("artifacts", {})
    if not isinstance(artifacts, dict):
        raise SnapshotError(
            f"{record}: artifacts must be an object, got {type(artifacts).__name__}"
        )
    tombstoned = raw.get("tombstoned", False)
    if not isinstance(tombstoned, bool):
        raise SnapshotError(f"{record}: tombstoned must be a boolean, got {tombstoned!r}")
    max_seq = raw.get("max_seq", 0)
    if not _is_int(max_seq) or int(max_seq) < 0:  # type: ignore[arg-type]
        raise SnapshotError(f"{record}: max_seq must be a non-negative integer, got {max_seq!r}")
    totals = raw.get("totals", {})
    if not isinstance(totals, dict):
        raise SnapshotError(f"{record}: totals must be an object, got {type(totals).__name__}")
    try:
        parsed = events.Totals.from_dict(totals)
    except events.InvalidEventError as exc:
        raise SnapshotError(f"{record}: {exc}") from exc
    return events.RecordState(
        record=record,
        status=status,
        fields=dict(fields),
        comments=list(comments),
        checkpoints=dict(checkpoints),
        artifacts=dict(artifacts),
        tombstoned=tombstoned,
        totals=parsed,
        max_seq=int(max_seq),  # type: ignore[arg-type]
    )


def to_lines(snapshot: Snapshot) -> list[str]:
    """*snapshot* as its lines, without their newlines: the header, then records in id order.

    Sorted by record id and dumped with ``sort_keys``, so folding one log twice produces a
    **byte-identical** file (§14) — which is what lets a rebuild be compared against a
    resumed refresh instead of argued about.
    """
    lines = [_dumps(snapshot.header.as_dict())]
    lines.extend(_dumps(record_to_dict(snapshot.records[key])) for key in sorted(snapshot.records))
    return lines


def read_header(path: Path | str) -> Header | None:
    """The header of the snapshot or checkpoint at *path*, reading **only its first line**.

    This is the function the whole header exists for: staleness costs one ``readline`` and
    one JSON decode, whatever the record count is.

    Returns:
        The header, or ``None`` when the file does not exist.

    Raises:
        SnapshotError: the file exists and its first line is not a usable header.
    """
    file_path = Path(path)
    try:
        with file_path.open("r", encoding="utf-8") as stream:
            first = stream.readline()
    except FileNotFoundError:
        return None
    if not first.strip():
        raise SnapshotError(f"{file_path.name} has no header line")
    return Header.from_dict(_object_from_line(first, file_path, 1))


def read_snapshot(path: Path | str) -> Snapshot | None:
    """The whole snapshot or checkpoint at *path*.

    Returns:
        The snapshot, or ``None`` when the file does not exist.

    Raises:
        SnapshotError: the file exists and is not a usable snapshot — including a repeated
            record id, which would make the fold depend on which line won.
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise SnapshotError(f"{file_path.name} has no header line")
    header = Header.from_dict(_object_from_line(lines[0], file_path, 1))
    records: dict[str, Any] = {}
    for number, line in enumerate(lines[1:], start=2):
        state = record_from_dict(_object_from_line(line, file_path, number))
        if state.record in records:
            raise SnapshotError(f"{file_path.name}:{number}: {state.record} appears twice")
        records[state.record] = state
    return Snapshot(header=header, records=records)


# --- the shrink guard ---------------------------------------------------------


@dataclass(frozen=True)
class Shrinkage:
    """What comparing a publish against the file it replaces found.

    Attributes:
        refused: True when the publish must not go ahead undeclared.
        reason: How the counts differed, or which uncomparable case applied. ``None`` when
            the comparison found no loss.
        existing: Records in the file replaced, ``None`` when none was compared.
        proposed: Records in the snapshot offered.
    """

    refused: bool
    reason: str | None
    existing: int | None
    proposed: int


def shrinkage(path: Path | str, snapshot: Snapshot) -> Shrinkage:
    """Whether publishing *snapshot* at *path* would hold fewer records than it replaces.

    R9's "no store shrinks silently", which the derived store had no answer to: the defect
    that bought it deleted 187 records, 47 of them open, and reported success. Both counts are
    of the **records each side holds** — never a header, which the fold being questioned wrote
    itself, and never a timestamp, which dates a file rather than saying what survived.

    An absent or unparseable file is nothing to compare against, so it publishes and names
    which of the two it was.
    """
    proposed = len(snapshot.records)
    try:
        current = read_snapshot(path)
    except SnapshotError as exc:
        reason = f"the file being replaced is unparseable, so nothing was compared: {exc}"
        return Shrinkage(False, reason, None, proposed)
    if current is None:
        return Shrinkage(False, "no file was there to compare against", None, proposed)
    existing = len(current.records)
    if proposed < existing:
        reason = f"this would publish {proposed} records over a file holding {existing}"
        return Shrinkage(True, reason, existing, proposed)
    return Shrinkage(False, None, existing, proposed)


def write_snapshot(path: Path | str, snapshot: Snapshot, *, allow_shrink: bool = False) -> Snapshot:
    """Publish *snapshot* at *path* by writing a temporary file and renaming it over.

    Atomic publication (§4.4), so a reader never sees a half-written derivative and a crash
    leaves either the old file or the new one. Two details that make that true rather than
    intended:

    - The temporary name carries this process's pid, so two concurrent refreshers cannot
      write into one another's partial file. They then rename the *same* content into place,
      which is why a refresh needs no lock: it reads the log and replaces a cache.
    - ``Path.replace`` rather than ``Path.rename``: on Windows a rename onto an existing
      file fails, which would leave every rebuild after the first one silently unpublished.

    Returns:
        The snapshot, so a caller can write and use it in one expression.

    Raises:
        SnapshotError: this would hold fewer records than the file it replaces and
            *allow_shrink* does not declare that intended (:func:`shrinkage`, which the flag
            skips along with the refusal). Both counts are in the message; nothing is written.
    """
    file_path = Path(path)
    if not allow_shrink:
        loss = shrinkage(file_path, snapshot)
        if loss.refused:
            raise SnapshotError(f"{file_path.name}: {loss.reason}")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = file_path.with_name(f"{file_path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for line in to_lines(snapshot):
                stream.write(line + "\n")
        temporary.replace(file_path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return snapshot


# --- paths --------------------------------------------------------------------


def snapshot_path(directory: Path | str) -> Path:
    """Where the derived snapshot of the ledger in *directory* lives."""
    return Path(directory) / SNAPSHOT_NAME


def log_path(directory: Path | str, period: str) -> Path:
    """The log file *period* names, built from :data:`events.LOG_GLOB`, not from a literal."""
    return Path(directory) / f"{_LOG_PREFIX}{period}{_LOG_SUFFIX}"


def checkpoint_path(directory: Path | str, period: str) -> Path:
    """The checkpoint file for the boundary that closed *period*."""
    return Path(directory) / f"{CHECKPOINT_PREFIX}{period}{_LOG_SUFFIX}"


def period_of(path: Path | str) -> str:
    """The period in a log or checkpoint file name — what sorts the ledger into order.

    Raises:
        SnapshotError: the name is neither a log nor a checkpoint.
    """
    name = Path(path).name
    if not name.endswith(_LOG_SUFFIX):
        raise SnapshotError(f"{name} is not a ledger file")
    stem = name[: -len(_LOG_SUFFIX)]
    for prefix in (_LOG_PREFIX, CHECKPOINT_PREFIX):
        if stem.startswith(prefix):
            return stem[len(prefix) :]
    raise SnapshotError(f"{name} is neither a log nor a checkpoint")


def checkpoint_paths(directory: Path | str) -> list[Path]:
    """Every checkpoint in *directory*, in period order."""
    return sorted(Path(directory).glob(CHECKPOINT_GLOB))


def latest_checkpoint(directory: Path | str) -> Path | None:
    """The checkpoint closest to now, or ``None`` if the ledger has never rotated."""
    found = checkpoint_paths(directory)
    return found[-1] if found else None


def logs_after(directory: Path | str, period: str) -> list[Path]:
    """Every log file whose period sorts after *period* — what a checkpoint leaves to fold."""
    return [path for path in events.log_paths(directory) if period_of(path) > period]


def derived_paths(directory: Path | str) -> list[Path]:
    """Every derived file present in the ledger: the snapshot and every checkpoint.

    The set a caller may delete — `fsck`'s "delete and rebuild, never repair in place". A
    log can never appear in it, which is the property that matters: this list is handed to
    a delete, and :data:`DERIVED_PATTERNS` sharing a directory with the truth is exactly
    where a too-wide pattern would destroy it.
    """
    ledger = Path(directory)
    found: list[Path] = []
    for pattern in DERIVED_PATTERNS:
        found.extend(sorted(ledger.glob(pattern)))
    return found


# --- the scan -----------------------------------------------------------------


@dataclass(frozen=True)
class LogTally:
    """What a scan of the logs says, having parsed exactly one line.

    Attributes:
        lines: Non-blank lines across every log file, in :data:`events.LOG_GLOB` order.
        last_event_id: The id on the last such line, or ``None`` when it does not parse.
    """

    lines: int = 0
    last_event_id: str | None = None


def scan_logs(directory: Path | str) -> LogTally:
    """Count the ledger's lines and read its tip id, without folding anything.

    Every log file is scanned rather than only the current one, because a union merge can
    append to an **archive**: a branch that carried older-period events lands them in the
    file whose period they belong to, and a tally that only watched the tip would report a
    grown ledger as unchanged.
    """
    return scan_paths(events.log_paths(directory))


def scan_paths(paths: Sequence[Path]) -> LogTally:
    """Scan *paths* in the order given: total non-blank lines, and the last one's event id."""
    lines = 0
    tip: bytes | None = None
    for path in paths:
        counted, last = _scan_log(path)
        lines += counted
        if last is not None:
            tip = last
    return LogTally(lines=lines, last_event_id=None if tip is None else _event_id(tip))


def _scan_log(path: Path) -> tuple[int, bytes | None]:
    r"""One log file's non-blank line count and its last complete line, still unparsed.

    Streamed in binary chunks and split on ``b"\n"`` rather than parsed line by line,
    because JSON-decoding every line *is* the fold cost the header exists to avoid. Exactly
    one line is decoded, by the caller, and only the last one.

    An unterminated final line is the torn-write signature `events.read_log` tolerates, so
    it counts only when it parses — a tip no fold consumed would make every read report a
    stale snapshot forever.
    """
    lines = 0
    last: bytes | None = None
    leftover = b""
    try:
        stream = path.open("rb")
    except FileNotFoundError:
        return 0, None
    with stream:
        while True:
            chunk = stream.read(SCAN_CHUNK_BYTES)
            if not chunk:
                break
            leftover += chunk
            pieces = leftover.split(b"\n")
            leftover = pieces.pop()
            for piece in pieces:
                if piece.strip():
                    lines += 1
                    last = piece
    if leftover.strip() and _event_id(leftover) is not None:
        lines += 1
        last = leftover
    return lines, last


def _event_id(line: bytes) -> str | None:
    """The event id on one raw log line, or ``None`` when the line is not an event."""
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        return events.from_json(text).id
    except events.InvalidEventError:
        return None


# --- staleness ----------------------------------------------------------------


@dataclass(frozen=True)
class Staleness:
    """Whether the snapshot still describes the log, and why not.

    Attributes:
        stale: True when the snapshot must be regenerated before it is believed.
        reason: What disagreed, for a hook or a `fsck` report to print. ``None`` when
            fresh.
        tally: The scan the answer was taken from.
        header: The snapshot's header, or ``None`` when there was none to read.
    """

    stale: bool
    reason: str | None
    tally: LogTally
    header: Header | None


def staleness(directory: Path | str) -> Staleness:
    """Whether the ledger's snapshot is current, from its header and a scan of the log.

    No fold, and not even a full read of the snapshot: the first line and a newline count
    decide it. The check is deliberately one-directional — a disagreement always means
    stale, while agreement means stale-free only because events are appended and never
    rewritten. A hand-edited log that kept both the line count and the tip is `fsck`'s
    problem, not something a cheap check can be made to catch.
    """
    ledger = Path(directory)
    tally = scan_logs(ledger)
    try:
        header = read_header(snapshot_path(ledger))
    except SnapshotError as exc:
        return Staleness(True, f"the snapshot's header is unusable: {exc}", tally, None)
    if header is None:
        return Staleness(True, "no snapshot has been written", tally, None)
    if header.log_lines != tally.lines:
        reason = f"the log holds {tally.lines} lines and the snapshot folded {header.log_lines}"
        return Staleness(True, reason, tally, header)
    if header.last_event_id != tally.last_event_id:
        reason = (
            f"the log's tip is {tally.last_event_id!r} and the snapshot's was "
            f"{header.last_event_id!r}"
        )
        return Staleness(True, reason, tally, header)
    return Staleness(False, None, tally, header)


# --- folding ------------------------------------------------------------------


@dataclass(frozen=True)
class Fold:
    """A fold of the ledger, and what it had to read to get there.

    Attributes:
        result: The ``events.FoldResult``.
        event_count: Events consumed, including those a checkpoint stood in for.
        quarantined: Lines the fold could not parse, from `events.read_log`.
        logs: The log files actually read — one file in steady state, all of them in a
            full-history fold.
        resumed_from: The checkpoint seeded into the fold, or ``None`` for a full fold.
    """

    result: Any
    event_count: int
    quarantined: list[Any] = field(default_factory=list)
    logs: list[Path] = field(default_factory=list)
    resumed_from: Path | None = None


def fold_all(directory: Path | str) -> Fold:
    """Fold the whole history: every file :data:`events.LOG_GLOB` finds, checkpoints ignored.

    The path that always works, and the one `fsck` uses: it is the only fold that can see a
    fork straddling a rotation boundary, and the only one whose answer does not depend on a
    derived file being right.
    """
    ledger = Path(directory)
    logs = events.log_paths(ledger)
    found, quarantined = events.read_events(ledger)
    return Fold(
        result=events.fold(found),
        event_count=len(found),
        quarantined=list(quarantined),
        logs=logs,
    )


def fold_resumed(directory: Path | str) -> Fold:
    """Fold steady state: the latest checkpoint plus the log files written after it.

    This is what the rotation checkpoint buys (§4.6): the bound is "current file, then one
    checkpoint", never "the whole history". Falls back to :func:`fold_all` when the ledger
    has never rotated, because then there is no archive to skip.

    **It also falls back when the archive has changed since the checkpoint was written**, and
    that is not a nicety. A union merge lands another branch's events in the file whose period
    they belong to, which can be a file this checkpoint already folded — so a shortcut that
    trusted the checkpoint unconditionally would publish a snapshot missing those events and
    then a header calling it current. The checkpoint's own ``log_lines`` is the test: it is
    trusted exactly while the files it folded still hold the lines it folded, which is a scan
    rather than a fold. An archive rewritten in place at an unchanged line count is `fsck`'s
    problem, the same boundary :func:`staleness` draws.

    Raises:
        SnapshotError: the checkpoint exists and is not usable. :func:`refresh` treats that
            as a speed problem rather than a correctness one and folds everything instead.
    """
    ledger = Path(directory)
    checkpoint = latest_checkpoint(ledger)
    if checkpoint is None:
        return fold_all(ledger)
    base = read_snapshot(checkpoint)
    if base is None:
        return fold_all(ledger)
    boundary = period_of(checkpoint)
    folded_before = [path for path in events.log_paths(ledger) if period_of(path) <= boundary]
    if scan_paths(folded_before).lines != base.header.log_lines:
        return fold_all(ledger)
    logs = logs_after(ledger, boundary)
    found: list[Any] = []
    quarantined: list[Any] = []
    for path in logs:
        parsed, bad = events.read_log(path)
        found.extend(parsed)
        quarantined.extend(bad)
    return Fold(
        result=events.fold(found, seed=base.records),
        event_count=base.header.event_count + len(found),
        quarantined=quarantined,
        logs=logs,
        resumed_from=checkpoint,
    )


def _snapshot_of(taken: Fold, tally: LogTally) -> Snapshot:
    """A snapshot carrying *taken*'s records under a header describing *tally*."""
    return Snapshot(
        header=Header(
            last_event_id=tally.last_event_id,
            event_count=taken.event_count,
            log_lines=tally.lines,
        ),
        records=dict(taken.result.records),
    )


def rebuild(directory: Path | str) -> Snapshot:
    """Regenerate the snapshot from the whole log and publish it.

    What `rebuild` means in §13: every derivative from the log alone. The scan runs first —
    see the module docstring; a header taken after the fold could report a stale snapshot as
    fresh, and that is the one error this design cannot absorb.
    """
    ledger = Path(directory)
    tally = scan_logs(ledger)
    return write_snapshot(snapshot_path(ledger), _snapshot_of(fold_all(ledger), tally))


def refresh(directory: Path | str) -> Snapshot:
    """Regenerate the snapshot from the checkpoint plus the current file, and publish it.

    The steady-state path, used by :func:`load` and by the hook. A checkpoint that cannot be
    read costs the shortcut and nothing else: this falls back to the full-history fold, which
    is what "derived and disposable" means in practice.
    """
    ledger = Path(directory)
    tally = scan_logs(ledger)
    try:
        taken = fold_resumed(ledger)
    except SnapshotError:
        taken = fold_all(ledger)
    return write_snapshot(snapshot_path(ledger), _snapshot_of(taken, tally))


def load(directory: Path | str) -> Snapshot:
    """The ledger's snapshot as a reader should get it, regenerated first if it is stale.

    The lazy half of §4's regeneration rule: no reader has to remember to rebuild, and a
    reader that does not check cannot exist, because this is the only read path. A snapshot
    the header cannot vouch for is replaced rather than trusted or repaired — and so is one
    whose header is fine and whose body is not, which is why the read is guarded rather than
    only the staleness check.
    """
    ledger = Path(directory)
    if not staleness(ledger).stale:
        try:
            current = read_snapshot(snapshot_path(ledger))
        except SnapshotError:
            current = None
        if current is not None:
            return current
    return refresh(ledger)


# --- rotation -----------------------------------------------------------------


@dataclass(frozen=True)
class Rotation:
    """What a rotation produced.

    Attributes:
        log: The new current file, empty, whose name sorts last so appends land in it.
        checkpoint: The boundary checkpoint, or ``None`` when there was no history to fold.
        archived: The log files that were already there — retained untouched, never pruned.
    """

    log: Path
    checkpoint: Path | None
    archived: list[Path] = field(default_factory=list)


def rotate(
    directory: Path | str,
    period: str,
    *,
    held_lock: Any = None,
    lock_timeout_s: float = events.DEFAULT_LOCK_TIMEOUT_S,
) -> Rotation:
    """Start a new period's log and publish the checkpoint that closes the old one.

    Nothing is deleted and nothing is moved: the previous files stay exactly as they are —
    "archived and never pruned" is a property of what this function *omits*, which is why
    the test asserts their bytes rather than their presence. The switch is the new name
    sorting last, which is all `events.append_target` looks at.

    Taken under the writer's lock, because it changes where an append lands: a rotation
    interleaved with an append could otherwise publish a checkpoint that omits an event
    already written to the file it is closing.

    Args:
        directory: The ledger directory. Created if it does not exist.
        period: The new period, matching :data:`PERIOD_PATTERN`. An **argument**, never a
            clock read (§9.5).
        held_lock: An already-held ``events.LedgerLock``, for a caller whose critical
            section is wider than one rotation.
        lock_timeout_s: How long to wait for the lock when taking one here.

    Raises:
        SnapshotError: the period is malformed, its file already exists, or its name would
            not sort after the current file — in which case appends would keep going to the
            older file and the rotation would be a silent no-op. Nothing is written.
        LockUnavailableError: from ``events.LedgerLock``. Retryable.
    """
    if not PERIOD_PATTERN.match(period):
        raise SnapshotError(f"period {period!r} must match {PERIOD_PATTERN.pattern}")
    ledger = Path(directory)
    ledger.mkdir(parents=True, exist_ok=True)
    lock = (
        held_lock if held_lock is not None else events.LedgerLock(ledger, timeout_s=lock_timeout_s)
    )
    acquired = held_lock is None
    if acquired:
        lock.acquire()
    try:
        target = log_path(ledger, period)
        archived = events.log_paths(ledger)
        if target.exists():
            raise SnapshotError(f"{target.name} already exists, so this is not a rotation")
        if archived and target.name <= archived[-1].name:
            raise SnapshotError(
                f"{target.name} does not sort after {archived[-1].name}: appends would keep "
                f"going to the older file and the rotation would be a silent no-op"
            )
        checkpoint = None
        if archived:
            checkpoint = checkpoint_path(ledger, period_of(archived[-1]))
            # The full-history fold, so the checkpoint carries **every** item's totals —
            # including one idle since before an earlier boundary. §4.6's bound depends on
            # that: a checkpoint resumed from its predecessor would drop nothing today and
            # would make the bound rest on the predecessor still existing.
            write_snapshot(checkpoint, _snapshot_of(fold_all(ledger), scan_logs(ledger)))
        try:
            target.touch(exist_ok=False)
        except FileExistsError as exc:
            raise SnapshotError(f"{target.name} appeared while the lock was held: {exc}") from exc
        return Rotation(log=target, checkpoint=checkpoint, archived=archived)
    finally:
        if acquired:
            lock.release()


# --- the hook entry point -----------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """Regenerate one ledger's snapshot, or report its staleness. The hook's entry point.

    Wired as a ``post-merge`` and ``post-checkout`` hook, this covers the case laziness
    cannot: a checkout or a merge changes the log wholesale, and the next reader would
    otherwise pay for the fold. ``--check`` writes nothing and exits 1 when stale, so a gate
    can assert freshness without producing it.

    There is no "refused" exit code, and that is the design rather than an omission: every
    unusable derivative on this path is *replaced* from the log, so the only outcomes are
    current, made current, and — under ``--check``, which writes nothing — stale.

    Returns:
        0 when the snapshot is current or was made current, 1 for ``--check`` on a stale
        ledger.
    """
    parser = argparse.ArgumentParser(
        description="Regenerate a tracker ledger's derived snapshot from its event log."
    )
    parser.add_argument("directory", help=f"the ledger directory holding {events.LOG_GLOB}")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="report staleness, write nothing, and exit 1 when the snapshot is stale",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="fold the whole history instead of resuming from the latest checkpoint",
    )
    args = parser.parse_args(argv)
    ledger = Path(args.directory)
    if not ledger.is_dir():
        # A hook wired into a repository with no tracker must be inert, not an error: this
        # is installed once and then runs on every checkout, including the ones before the
        # ledger exists.
        print(_dumps({"directory": str(ledger), "ledger": False, "written": False}))
        return 0
    state = staleness(ledger)
    report: dict[str, object] = {
        "directory": str(ledger),
        "ledger": True,
        "stale": state.stale,
        "reason": state.reason,
        "log_lines": state.tally.lines,
        "last_event_id": state.tally.last_event_id,
        "written": False,
    }
    if args.check:
        print(_dumps(report))
        return 1 if state.stale else 0
    if state.stale or args.full:
        published = rebuild(ledger) if args.full else refresh(ledger)
        report["written"] = True
        report["event_count"] = published.header.event_count
        report["records"] = len(published.records)
    print(_dumps(report))
    return 0


# --- shared helpers -----------------------------------------------------------


def _dumps(obj: Mapping[str, object]) -> str:
    """One JSON line: sorted keys and no spaces, so two folds render identically."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _object_from_line(line: str, path: Path, number: int) -> Mapping[str, object]:
    """One line of a derived file as a JSON object.

    Raises:
        SnapshotError: the line is not a JSON object. Named by file and line number, the
            same way `events.Quarantine` names a bad log line — except that here the answer
            is to rebuild rather than to quarantine.
    """
    try:
        raw = json.loads(line)
    except ValueError as exc:
        raise SnapshotError(f"{path.name}:{number}: not JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SnapshotError(f"{path.name}:{number}: not a JSON object: {type(raw).__name__}")
    return raw


def _is_int(value: object) -> bool:
    """True for a genuine integer. ``bool`` is excluded: ``True + 1`` is 2, silently."""
    return isinstance(value, int) and not isinstance(value, bool)


if __name__ == "__main__":
    sys.exit(main())
