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

_HERE = Path(__file__).resolve().parent
_EVENTS_MODULE_NAME = "basicly_tracker_kit_events"


def _load_events() -> Any:

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


_LOG_PREFIX, _, _LOG_SUFFIX = events.LOG_GLOB.partition("*")

SNAPSHOT_NAME = "snapshot" + _LOG_SUFFIX
CHECKPOINT_PREFIX = "checkpoint-"
CHECKPOINT_GLOB = CHECKPOINT_PREFIX + "*" + _LOG_SUFFIX

DERIVED_PATTERNS = (SNAPSHOT_NAME, CHECKPOINT_GLOB)

SNAPSHOT_VERSION = 3

PERIOD_PATTERN = re.compile(r"^[0-9]{4,}[a-z0-9]*$")

SCAN_CHUNK_BYTES = 65536


class SnapshotError(events.LedgerError):
    pass


@dataclass(frozen=True)
class Header:
    last_event_id: str | None = None
    event_count: int = 0
    log_lines: int = 0
    version: int = SNAPSHOT_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "last_event_id": self.last_event_id,
            "event_count": self.event_count,
            "log_lines": self.log_lines,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Header:

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


@dataclass(frozen=True)
class Snapshot:
    header: Header = field(default_factory=Header)
    records: dict[str, Any] = field(default_factory=dict)


def record_to_dict(state: Any) -> dict[str, object]:

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
        "dates": dict(state.dates),
        "contested": list(state.contested),
    }


def record_from_dict(raw: Mapping[str, object]) -> Any:

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
    dates = raw.get("dates", {})
    if not isinstance(dates, dict) or not all(
        value is None or isinstance(value, str) for value in dates.values()
    ):
        raise SnapshotError(f"{record}: dates map a name to a time or null, got {dates!r}")
    contested = raw.get("contested", [])
    if not isinstance(contested, list) or not all(isinstance(name, str) for name in contested):
        raise SnapshotError(f"{record}: contested must be a list of names, got {contested!r}")
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
        dates={**events.RecordState(record).dates, **dates},
        contested=list(contested),
    )


def to_lines(snapshot: Snapshot) -> list[str]:

    lines = [_dumps(snapshot.header.as_dict())]
    lines.extend(_dumps(record_to_dict(snapshot.records[key])) for key in sorted(snapshot.records))
    return lines


def read_header(path: Path | str) -> Header | None:

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


@dataclass(frozen=True)
class Shrinkage:
    refused: bool
    reason: str | None
    existing: int | None
    proposed: int


def shrinkage(path: Path | str, snapshot: Snapshot) -> Shrinkage:

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


def snapshot_path(directory: Path | str) -> Path:
    return Path(directory) / SNAPSHOT_NAME


def log_path(directory: Path | str, period: str) -> Path:
    return Path(directory) / f"{_LOG_PREFIX}{period}{_LOG_SUFFIX}"


def checkpoint_path(directory: Path | str, period: str) -> Path:
    return Path(directory) / f"{CHECKPOINT_PREFIX}{period}{_LOG_SUFFIX}"


def period_of(path: Path | str) -> str:

    name = Path(path).name
    if not name.endswith(_LOG_SUFFIX):
        raise SnapshotError(f"{name} is not a ledger file")
    stem = name[: -len(_LOG_SUFFIX)]
    for prefix in (_LOG_PREFIX, CHECKPOINT_PREFIX):
        if stem.startswith(prefix):
            return stem[len(prefix) :]
    raise SnapshotError(f"{name} is neither a log nor a checkpoint")


def checkpoint_paths(directory: Path | str) -> list[Path]:
    return sorted(Path(directory).glob(CHECKPOINT_GLOB))


def latest_checkpoint(directory: Path | str) -> Path | None:
    found = checkpoint_paths(directory)
    return found[-1] if found else None


def logs_after(directory: Path | str, period: str) -> list[Path]:
    return [path for path in events.log_paths(directory) if period_of(path) > period]


def derived_paths(directory: Path | str) -> list[Path]:

    ledger = Path(directory)
    found: list[Path] = []
    for pattern in DERIVED_PATTERNS:
        found.extend(sorted(ledger.glob(pattern)))
    return found


@dataclass(frozen=True)
class LogTally:
    lines: int = 0
    last_event_id: str | None = None


def scan_logs(directory: Path | str) -> LogTally:

    return scan_paths(events.ledger_paths(directory))


def scan_paths(paths: Sequence[Path]) -> LogTally:
    lines = 0
    tip: bytes | None = None
    for path in paths:
        counted, last = _scan_log(path)
        lines += counted
        if last is not None:
            tip = last
    return LogTally(lines=lines, last_event_id=None if tip is None else _event_id(tip))


def _scan_log(path: Path) -> tuple[int, bytes | None]:

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
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        return events.from_json(text).id
    except events.InvalidEventError:
        return None


@dataclass(frozen=True)
class Staleness:
    stale: bool
    reason: str | None
    tally: LogTally
    header: Header | None


def staleness(directory: Path | str) -> Staleness:

    ledger = Path(directory)
    tally = scan_logs(ledger)
    try:
        header = read_header(snapshot_path(ledger))
    except SnapshotError as exc:
        return Staleness(True, f"the snapshot's header is unusable: {exc}", tally, None)
    if header is None:
        return Staleness(True, "no snapshot has been written", tally, None)
    if header.version != SNAPSHOT_VERSION:
        reason = f"the snapshot is format {header.version} and this kit writes {SNAPSHOT_VERSION}"
        return Staleness(True, reason, tally, header)
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


@dataclass(frozen=True)
class Fold:
    result: Any
    event_count: int
    quarantined: list[Any] = field(default_factory=list)
    logs: list[Path] = field(default_factory=list)
    resumed_from: Path | None = None


def fold_all(directory: Path | str) -> Fold:

    ledger = Path(directory)
    logs = events.ledger_paths(ledger)
    found, quarantined = events.read_events(ledger)
    return Fold(
        result=events.fold(found),
        event_count=len(found),
        quarantined=list(quarantined),
        logs=logs,
    )


def fold_resumed(directory: Path | str) -> Fold:

    ledger = Path(directory)
    checkpoint = latest_checkpoint(ledger)
    if checkpoint is None:
        return fold_all(ledger)
    base = read_snapshot(checkpoint)
    if base is None or base.header.version != SNAPSHOT_VERSION:
        return fold_all(ledger)
    boundary = period_of(checkpoint)
    folded_before = [path for path in events.log_paths(ledger) if period_of(path) <= boundary]
    if scan_paths(folded_before).lines != base.header.log_lines:
        return fold_all(ledger)
    logs = logs_after(ledger, boundary) + events.pending_paths(ledger)
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
    return Snapshot(
        header=Header(
            last_event_id=tally.last_event_id,
            event_count=taken.event_count,
            log_lines=tally.lines,
        ),
        records=dict(taken.result.records),
    )


def rebuild(directory: Path | str) -> Snapshot:

    ledger = Path(directory)
    tally = scan_logs(ledger)
    return write_snapshot(snapshot_path(ledger), _snapshot_of(fold_all(ledger), tally))


def refresh(directory: Path | str) -> Snapshot:

    ledger = Path(directory)
    tally = scan_logs(ledger)
    try:
        taken = fold_resumed(ledger)
    except SnapshotError:
        taken = fold_all(ledger)
    return write_snapshot(snapshot_path(ledger), _snapshot_of(taken, tally))


def load(directory: Path | str) -> Snapshot:

    ledger = Path(directory)
    if not staleness(ledger).stale:
        try:
            current = read_snapshot(snapshot_path(ledger))
        except SnapshotError:
            current = None
        if current is not None:
            return current
    return refresh(ledger)


@dataclass(frozen=True)
class Compaction:
    trunk: Path
    shards: tuple[Path, ...] = ()
    appended: int = 0
    duplicates: int = 0


def compact(
    directory: Path | str,
    *,
    writers: Sequence[str] = (),
    held_lock: Any = None,
    lock_timeout_s: float = events.DEFAULT_LOCK_TIMEOUT_S,
) -> Compaction:

    ledger = Path(directory)
    ledger.mkdir(parents=True, exist_ok=True)
    lock = (
        held_lock if held_lock is not None else events.LedgerLock(ledger, timeout_s=lock_timeout_s)
    )
    acquired = held_lock is None
    if acquired:
        lock.acquire()
    try:
        wanted = frozenset(writers)
        shards = [
            path
            for path in events.pending_paths(ledger)
            if not wanted or events.writer_of(path) in wanted
        ]
        trunk = events.append_target(ledger, writer="")
        if not shards:
            return Compaction(trunk=trunk, shards=())
        known = {event.id for event in events.read_events_from(events.log_paths(ledger))[0]}
        carried: list[str] = []
        duplicates = 0
        for path in shards:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = events.from_json(line)
                except events.InvalidEventError:
                    carried.append(line)
                    continue
                if event.id in known:
                    duplicates += 1
                    continue
                known.add(event.id)
                carried.append(line)
        if carried:
            events.append_lines(trunk, carried)
        for path in shards:
            path.unlink()
        return Compaction(
            trunk=trunk, shards=tuple(shards), appended=len(carried), duplicates=duplicates
        )
    finally:
        if acquired:
            lock.release()


@dataclass(frozen=True)
class Rotation:
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
        if held := events.pending_paths(ledger):
            raise SnapshotError(
                f"{len(held)} pending shard(s) hold uncompacted events "
                f"({', '.join(path.name for path in held)}); a rotation would write a "
                f"checkpoint the resumed fold cannot match, so compact before rotating"
            )
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
            write_snapshot(checkpoint, _snapshot_of(fold_all(ledger), scan_logs(ledger)))
        try:
            target.touch(exist_ok=False)
        except FileExistsError as exc:
            raise SnapshotError(f"{target.name} appeared while the lock was held: {exc}") from exc
        return Rotation(log=target, checkpoint=checkpoint, archived=archived)
    finally:
        if acquired:
            lock.release()


def main(argv: Sequence[str] | None = None) -> int:

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


def _dumps(obj: Mapping[str, object]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _object_from_line(line: str, path: Path, number: int) -> Mapping[str, object]:

    try:
        raw = json.loads(line)
    except ValueError as exc:
        raise SnapshotError(f"{path.name}:{number}: not JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SnapshotError(f"{path.name}:{number}: not a JSON object: {type(raw).__name__}")
    return raw


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


if __name__ == "__main__":
    sys.exit(main())
