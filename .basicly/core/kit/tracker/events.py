from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType


class LedgerError(Exception):
    pass


class InvalidEventError(LedgerError):
    pass


class LockUnavailableError(LedgerError):
    retryable = True


_HERE = Path(__file__).resolve().parent
_IDS_MODULE_NAME = "basicly_tracker_kit_ids"


def _load_ids() -> object:

    cached = sys.modules.get(_IDS_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_IDS_MODULE_NAME, _HERE / "ids.py")
    if spec is None or spec.loader is None:
        raise LedgerError("the tracker kit's ids.py is missing from beside events.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_IDS_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


ids = _load_ids()


LOG_GLOB = "events-*.jsonl"
INITIAL_LOG_NAME = "events-0001.jsonl"

PENDING_GLOB = "pending-*.jsonl"
_PENDING_PREFIX, _, _PENDING_SUFFIX = PENDING_GLOB.partition("*")
WRITER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

GIT_DIR_NAME = ".git"
_GIT_HEAD = "HEAD"
_GIT_REF_MARK = "ref:"
_GIT_DIR_MARK = "gitdir:"
_GIT_BRANCH_PREFIX = "refs/heads/"
DETACHED_WRITER = "detached"

LOCK_NAME = ".events.lock"

TRUNCATABLE_KEYS = frozenset({"text", "value", "output", "detail"})

FOLD_READ_KEYS = frozenset({
    "approved_by",
    "artifact",
    "asserted_at",
    "asserted_by",
    "body",
    "checkpoint",
    "edge_type",
    "from",
    "gate",
    "import_digest",
    "imported_from",
    "name",
    "passed",
    "provenance",
    "provider",
    "source_id",
    "spend_micros",
    "status",
    "target",
    "to",
    "type",
    "value",
})

BUFFER_CHUNK_BYTES = 8192
MAX_TEXT_BYTES = 4096

DEFAULT_LOCK_TIMEOUT_S = 5.0
LOCK_STALE_AFTER_S = 30.0
LOCK_POLL_S = 0.01

MAX_LOCK_STEALS = 8

KIND_CREATED = "created"
KIND_FIELD = "field"
KIND_STATUS = "status"
KIND_NOTE = "note"
KIND_COMMENT = "comment"
KIND_DISPATCH = "dispatch"
KIND_TOMBSTONE = "tombstone"
KIND_EDGE = "edge"
KIND_EDGE_RETRACTED = "edge_retracted"
KIND_GATE = "gate"
KIND_CHECKPOINT = "checkpoint"
KIND_ARTIFACT = "artifact"
KIND_WITHDRAWN = "withdrawn"

KNOWN_KINDS = frozenset({
    KIND_CREATED,
    KIND_FIELD,
    KIND_STATUS,
    KIND_NOTE,
    KIND_COMMENT,
    KIND_DISPATCH,
    KIND_TOMBSTONE,
    KIND_EDGE,
    KIND_EDGE_RETRACTED,
    KIND_GATE,
    KIND_CHECKPOINT,
    KIND_ARTIFACT,
    KIND_WITHDRAWN,
})

KIND_TEXT_BYTES = MappingProxyType({
    KIND_CREATED: None,
    KIND_ARTIFACT: None,
    KIND_FIELD: MAX_TEXT_BYTES,
    KIND_STATUS: MAX_TEXT_BYTES,
    KIND_NOTE: MAX_TEXT_BYTES,
    KIND_COMMENT: MAX_TEXT_BYTES,
    KIND_DISPATCH: MAX_TEXT_BYTES,
    KIND_TOMBSTONE: MAX_TEXT_BYTES,
    KIND_EDGE: MAX_TEXT_BYTES,
    KIND_EDGE_RETRACTED: MAX_TEXT_BYTES,
    KIND_GATE: MAX_TEXT_BYTES,
    KIND_CHECKPOINT: MAX_TEXT_BYTES,
    KIND_WITHDRAWN: MAX_TEXT_BYTES,
})

PROSE_KINDS = frozenset({KIND_NOTE, KIND_COMMENT})

APPLIED = "applied"
DELEGATED = "delegated"
UNKNOWN = "unknown"

DELEGATED_KINDS = MappingProxyType({
    KIND_EDGE: "provenance.fold_edges",
    KIND_EDGE_RETRACTED: "differential.views_from_events",
    KIND_GATE: "gates.fold_gates",
})

KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

EVENT_FAMILY = "ev"

KNOWN_FIELDS = frozenset({"id", "record", "seq", "kind", "actor", "ts", "payload", "totals"})

WITHDRAWN_PLACEHOLDER = ""
WITHDRAWN_SUFFIX = "_withdrawn"
WITHDRAWN_FROM = "withdrawn_from"

WITHDRAWN_TARGET = "target"
WITHDRAWN_REASON = "reason"

UNATTRIBUTED_ACTOR = "unattributed:no-actor-supplied"


@dataclass(frozen=True)
class Totals:
    events: int = 0
    attempts: int = 0
    spend_micros: int = 0
    status: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "events": self.events,
            "attempts": self.attempts,
            "spend_micros": self.spend_micros,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Totals:

        values = {}
        for name in ("events", "attempts", "spend_micros"):
            value = raw.get(name, 0)
            if not _is_int(value):
                raise InvalidEventError(f"totals.{name} must be an integer, got {value!r}")
            values[name] = int(value)  # type: ignore[arg-type]
        status = raw.get("status")
        if status is not None and not isinstance(status, str):
            raise InvalidEventError(f"totals.status must be a string or null, got {status!r}")
        return cls(status=status, **values)


def accumulate(previous: Totals, kind: str, payload: Mapping[str, object]) -> Totals:

    spend = payload.get("spend_micros", 0)
    if not _is_int(spend):
        raise InvalidEventError(
            f"spend_micros must be an integer number of micro-units, got {spend!r}: "
            f"a float sum is exact only for the order it was taken in"
        )
    status = previous.status
    if kind == KIND_STATUS:
        recorded = payload.get("status")
        if not isinstance(recorded, str):
            raise InvalidEventError(
                f"a {KIND_STATUS} event needs a string status, got {recorded!r}"
            )
        status = recorded
    return Totals(
        events=previous.events + 1,
        attempts=previous.attempts + (1 if kind == KIND_DISPATCH else 0),
        spend_micros=previous.spend_micros + int(spend),  # type: ignore[arg-type]
        status=status,
    )


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Draft:
    record: str
    kind: str
    payload: Mapping[str, object] = field(default_factory=dict)
    actor: str = ""
    generation: int = 1


@dataclass(frozen=True)
class Event:
    id: str
    record: str
    seq: int
    kind: str
    actor: str
    ts: str
    payload: Mapping[str, object] = field(default_factory=dict)
    totals: Totals = field(default_factory=Totals)
    extra: Mapping[str, object] = field(default_factory=dict)


def canonical_key(event: Event) -> tuple[str, int, str]:

    return (event.record, event.seq, event.id)


def canonical_order(events: Iterable[Event]) -> list[Event]:

    seen: set[str] = set()
    ordered = []
    for event in sorted(events, key=canonical_key):
        if event.id in seen:
            continue
        seen.add(event.id)
        ordered.append(event)
    return ordered


def event_id_for(
    record: str, kind: str, payload: Mapping[str, object], *, generation: int = 1
) -> str:

    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return ids.evidence_id(  # type: ignore[attr-defined]
        record, kind, content, family=EVENT_FAMILY, generation=generation
    )


def to_json(event: Event) -> str:

    obj: dict[str, object] = dict(event.extra)
    obj.update({
        "id": event.id,
        "record": event.record,
        "seq": event.seq,
        "kind": event.kind,
        "actor": event.actor,
        "ts": event.ts,
        "payload": dict(event.payload),
        "totals": event.totals.as_dict(),
    })
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def from_json(line: str) -> Event:

    try:
        raw = json.loads(line)
    except ValueError as exc:
        raise InvalidEventError(f"not JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise InvalidEventError(f"not a JSON object: {type(raw).__name__}")
    for name in ("id", "record", "kind", "actor", "ts"):
        if not isinstance(raw.get(name), str):
            raise InvalidEventError(f"{name} must be a string, got {raw.get(name)!r}")
    if not _is_int(raw.get("seq")):
        raise InvalidEventError(f"seq must be an integer, got {raw.get('seq')!r}")
    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        raise InvalidEventError(f"payload must be an object, got {type(payload).__name__}")
    totals = raw.get("totals", {})
    if not isinstance(totals, dict):
        raise InvalidEventError(f"totals must be an object, got {type(totals).__name__}")
    return Event(
        id=raw["id"],
        record=raw["record"],
        seq=int(raw["seq"]),
        kind=raw["kind"],
        actor=raw["actor"],
        ts=raw["ts"],
        payload=payload,
        totals=Totals.from_dict(totals),
        extra={key: value for key, value in raw.items() if key not in KNOWN_FIELDS},
    )


@dataclass(frozen=True)
class Withdrawal:
    record: str
    target: str
    reason: str
    at: str


@dataclass
class RecordState:
    record: str
    status: str | None = None
    fields: dict[str, object] = field(default_factory=dict)
    comments: list[str] = field(default_factory=list)
    checkpoints: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, object] = field(default_factory=dict)
    tombstoned: bool = False
    totals: Totals = field(default_factory=Totals)
    max_seq: int = 0


@dataclass
class FoldResult:
    records: dict[str, RecordState] = field(default_factory=dict)
    delegated_kinds: dict[str, int] = field(default_factory=dict)
    unknown_kinds: dict[str, int] = field(default_factory=dict)
    duplicate_ids: list[str] = field(default_factory=list)
    forked: list[str] = field(default_factory=list)
    mismatched_totals: list[str] = field(default_factory=list)
    withdrawals: list[Withdrawal] = field(default_factory=list)


def _apply_created(state: RecordState, payload: Mapping[str, object]) -> None:
    state.fields.update(payload)


def _apply_field(state: RecordState, payload: Mapping[str, object]) -> None:
    name = payload.get("name")
    if not isinstance(name, str):
        raise InvalidEventError(f"a {KIND_FIELD} event needs a string name, got {name!r}")
    state.fields[name] = payload.get("value")


def _apply_status(state: RecordState, payload: Mapping[str, object]) -> None:
    state.status = payload["status"]  # type: ignore[assignment]


def _apply_note(state: RecordState, payload: Mapping[str, object]) -> None:
    text = payload.get("text", "")
    if not isinstance(text, str):
        raise InvalidEventError(f"a {KIND_NOTE} event needs string text, got {text!r}")
    state.comments.append(text)


def _apply_checkpoint(state: RecordState, payload: Mapping[str, object]) -> None:

    name = payload.get("checkpoint")
    if not isinstance(name, str) or not name:
        raise InvalidEventError(f"a {KIND_CHECKPOINT} event needs a checkpoint name, got {name!r}")
    approver = payload.get("approved_by", "")
    if not isinstance(approver, str):
        raise InvalidEventError(
            f"a {KIND_CHECKPOINT} event needs a string approved_by, got {approver!r}"
        )
    state.checkpoints[name] = approver


def _apply_artifact(state: RecordState, payload: Mapping[str, object]) -> None:

    kind = payload.get("artifact")
    if not isinstance(kind, str) or not kind:
        raise InvalidEventError(f"an {KIND_ARTIFACT} event needs an artifact kind, got {kind!r}")
    state.artifacts[kind] = payload.get("body")


def _withdrawal_facts(payload: Mapping[str, object]) -> tuple[str, str]:

    target = payload.get(WITHDRAWN_TARGET)
    reason = payload.get(WITHDRAWN_REASON)
    if not isinstance(target, str) or not target:
        raise InvalidEventError(
            f"a {KIND_WITHDRAWN} event needs the {WITHDRAWN_TARGET} event id, got {target!r}"
        )
    if not isinstance(reason, str) or not reason:
        raise InvalidEventError(
            f"a {KIND_WITHDRAWN} event needs a {WITHDRAWN_REASON}, got {reason!r}"
        )
    return target, reason


def _apply_withdrawn(result: FoldResult, event: Event) -> None:
    target, reason = _withdrawal_facts(event.payload)
    result.withdrawals.append(
        Withdrawal(record=event.record, target=target, reason=reason, at=event.ts)
    )


def _apply_tombstone(state: RecordState, payload: Mapping[str, object]) -> None:  # noqa: ARG001
    state.tombstoned = True


_HANDLERS: dict[str, Callable[[RecordState, Mapping[str, object]], None]] = {
    KIND_CREATED: _apply_created,
    KIND_FIELD: _apply_field,
    KIND_STATUS: _apply_status,
    KIND_NOTE: _apply_note,
    KIND_COMMENT: _apply_note,
    KIND_TOMBSTONE: _apply_tombstone,
    KIND_CHECKPOINT: _apply_checkpoint,
    KIND_ARTIFACT: _apply_artifact,
}

APPLIED_KINDS = frozenset(_HANDLERS) | {KIND_DISPATCH, KIND_WITHDRAWN}


def classify_kind(kind: str) -> str:

    if kind in APPLIED_KINDS:
        return APPLIED
    if kind in DELEGATED_KINDS:
        return DELEGATED
    return UNKNOWN


def _resumed(state: RecordState) -> RecordState:
    return RecordState(
        record=state.record,
        status=state.status,
        fields=dict(state.fields),
        comments=list(state.comments),
        checkpoints=dict(state.checkpoints),
        artifacts=dict(state.artifacts),
        tombstoned=state.tombstoned,
        totals=state.totals,
        max_seq=state.max_seq,
    )


def fold(events: Iterable[Event], *, seed: Mapping[str, RecordState] | None = None) -> FoldResult:

    collected = list(events)
    result = FoldResult()
    if seed is not None:
        result.records = {name: _resumed(state) for name, state in seed.items()}
    counts: dict[str, int] = {}
    for event in collected:
        counts[event.id] = counts.get(event.id, 0) + 1
    result.duplicate_ids = sorted(key for key, count in counts.items() if count > 1)
    ordered = canonical_order(collected)
    claimed: dict[str, set[int]] = {}
    for event in ordered:
        state = result.records.setdefault(event.record, RecordState(record=event.record))
        sequences = claimed.setdefault(event.record, set())
        if event.seq in sequences and event.record not in result.forked:
            result.forked.append(event.record)
        sequences.add(event.seq)
        state.max_seq = max(state.max_seq, event.seq)
        state.totals = accumulate(state.totals, event.kind, event.payload)
        if event.totals != state.totals:
            result.mismatched_totals.append(event.id)
        if event.kind == KIND_WITHDRAWN:
            _apply_withdrawn(result, event)
            continue
        handler = _HANDLERS.get(event.kind)
        if handler is not None:
            handler(state, event.payload)
            continue
        classified = classify_kind(event.kind)
        if classified == DELEGATED:
            result.delegated_kinds[event.kind] = result.delegated_kinds.get(event.kind, 0) + 1
        elif classified == UNKNOWN:
            result.unknown_kinds[event.kind] = result.unknown_kinds.get(event.kind, 0) + 1
    return result


@dataclass(frozen=True)
class Quarantine:
    path: Path
    line_number: int
    line: str
    reason: str


def log_paths(directory: Path | str) -> list[Path]:

    return sorted(Path(directory).glob(LOG_GLOB))


def pending_paths(directory: Path | str) -> list[Path]:

    return sorted(Path(directory).glob(PENDING_GLOB))


def ledger_paths(directory: Path | str) -> list[Path]:

    return log_paths(directory) + pending_paths(directory)


def pending_path(directory: Path | str, writer: str) -> Path:

    if not WRITER_PATTERN.match(writer):
        raise LedgerError(
            f"writer {writer!r} must match {WRITER_PATTERN.pattern}: it becomes a file name, "
            f"so a slash or a leading dot would escape the ledger directory"
        )
    return Path(directory) / f"{_PENDING_PREFIX}{writer}{_PENDING_SUFFIX}"


def writer_of(path: Path | str) -> str:

    name = Path(path).name
    if not name.startswith(_PENDING_PREFIX) or not name.endswith(_PENDING_SUFFIX):
        raise LedgerError(f"{name} is not a pending shard")
    return name[len(_PENDING_PREFIX) : -len(_PENDING_SUFFIX)]


def _git_dir(start: Path) -> Path | None:

    for directory in (start, *start.parents):
        candidate = directory / GIT_DIR_NAME
        if candidate.is_dir():
            return candidate
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8").strip()
            if text.startswith(_GIT_DIR_MARK):
                linked = Path(text[len(_GIT_DIR_MARK) :].strip())
                return linked if linked.is_absolute() else (directory / linked).resolve()
    return None


def _slug(text: str) -> str:

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.")
    return cleaned[:64] or DETACHED_WRITER


def derive_writer(directory: Path | str) -> str | None:

    git_dir = _git_dir(Path(directory).resolve())
    if git_dir is None:
        return None
    try:
        head = (git_dir / _GIT_HEAD).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith(_GIT_REF_MARK):
        return DETACHED_WRITER
    ref = head[len(_GIT_REF_MARK) :].strip()
    branch = ref.removeprefix(_GIT_BRANCH_PREFIX)
    return _slug(branch)


def read_log(path: Path | str) -> tuple[list[Event], list[Quarantine]]:

    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], []
    complete = text.endswith("\n")
    lines = text.splitlines()
    events: list[Event] = []
    quarantined: list[Quarantine] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            events.append(from_json(line))
        except InvalidEventError as exc:
            torn = number == len(lines) and not complete
            if not torn:
                quarantined.append(Quarantine(file_path, number, line, str(exc)))
    return events, quarantined


def read_events_from(paths: Sequence[Path]) -> tuple[list[Event], list[Quarantine]]:
    events: list[Event] = []
    quarantined: list[Quarantine] = []
    for path in paths:
        found, bad = read_log(path)
        events.extend(found)
        quarantined.extend(bad)
    return events, quarantined


def read_events(directory: Path | str) -> tuple[list[Event], list[Quarantine]]:
    return read_events_from(ledger_paths(directory))


def append_target(directory: Path | str, *, writer: str | None = None) -> Path:

    chosen = writer if writer is not None else derive_writer(directory)
    if chosen:
        return pending_path(directory, chosen)
    paths = log_paths(directory)
    return paths[-1] if paths else Path(directory) / INITIAL_LOG_NAME


def default_pid_liveness(pid: int) -> bool | None:

    if os.name == "nt":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class LedgerLock:
    def __init__(  # noqa: PLR0913 — one keyword per injected seam; see the class docstring
        self,
        directory: Path | str,
        *,
        timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
        stale_after_s: float = LOCK_STALE_AFTER_S,
        poll_s: float = LOCK_POLL_S,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        pid: int | None = None,
        is_alive: Callable[[int], bool | None] = default_pid_liveness,
    ) -> None:
        self.path = Path(directory) / LOCK_NAME
        self._timeout_s = timeout_s
        self._stale_after_s = stale_after_s
        self._poll_s = poll_s
        self._monotonic = monotonic
        self._sleep = sleep
        self._pid = os.getpid() if pid is None else pid
        self._is_alive = is_alive
        self._held = False
        self.steals = 0

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self) -> LedgerLock:

        deadline = self._monotonic() + self._timeout_s
        while True:
            if self._try_create():
                self._held = True
                return self
            if self._steal_if_stale():
                if self.steals > MAX_LOCK_STEALS:
                    raise LockUnavailableError(
                        f"{self.path} went stale {self.steals} times in one acquire: "
                        f"the staleness answers are wrong, not the lock"
                    )
                continue
            if self._monotonic() >= deadline:
                raise LockUnavailableError(
                    f"another writer holds {self.path} after {self._timeout_s}s"
                )
            self._sleep(self._poll_s)

    def release(self) -> None:

        self._held = False
        record = self._read_holder()
        if record is not None and record.get("pid") != self._pid:
            return
        try:
            self.path.unlink()
        except FileNotFoundError:
            return

    def __enter__(self) -> LedgerLock:
        return self.acquire()

    def __exit__(self, *_exc: object) -> None:
        self.release()

    def _try_create(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump({"pid": self._pid, "monotonic": self._monotonic()}, stream, sort_keys=True)
        return True

    def _read_holder(self) -> dict[str, object] | None:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            return None
        try:
            record = json.loads(raw)
        except ValueError:
            return None
        return record if isinstance(record, dict) else None

    def _steal_if_stale(self) -> bool:
        record = self._read_holder()
        if record is None:
            return self._steal()
        pid = record.get("pid")
        if _is_int(pid) and self._is_alive(int(pid)) is False:  # type: ignore[arg-type]
            return self._steal()
        stamp = record.get("monotonic")
        if not isinstance(stamp, (int, float)) or isinstance(stamp, bool):
            return self._steal()
        age = self._monotonic() - float(stamp)
        if age < 0.0 or age > self._stale_after_s:
            return self._steal()
        return False

    def _steal(self) -> bool:
        self.steals += 1
        try:
            self.path.unlink()
        except FileNotFoundError:
            return True
        return True


def _stamp(seconds: float) -> str:

    return (
        datetime
        .fromtimestamp(seconds, tz=timezone.utc)  # noqa: UP017 — 3.11+ alias
        .isoformat()
        .replace("+00:00", "Z")
    )


def _truncate(text: str, max_bytes: int) -> tuple[str, int]:

    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, len(encoded)
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), len(encoded)


def _redacted(value: object, redact: Callable[[str], str] | None) -> object:
    if isinstance(value, str):
        return value if redact is None else redact(value)
    if isinstance(value, dict):
        return {key: _redacted(item, redact) for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted(item, redact) for item in value]
    return value


def _text_bound(kind: str | None, max_text_bytes: int) -> tuple[int | None, int | None]:

    if kind is None:
        return None, None
    if kind not in KIND_TEXT_BYTES:
        return None, max_text_bytes
    declared = KIND_TEXT_BYTES[kind]
    return (None if declared is None else min(declared, max_text_bytes)), None


def _text_size(value: object) -> int:

    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, dict):
        return sum(_text_size(key) + _text_size(item) for key, item in value.items())
    if isinstance(value, list):
        return sum(_text_size(item) for item in value)
    return 0


def _refuse_unbounded(kind: str, payload: Mapping[str, object], refuse_over: int) -> None:

    for key, value in payload.items():
        if key in FOLD_READ_KEYS:
            continue
        size = _text_size(value)
        if size > refuse_over:
            raise InvalidEventError(
                f"kind {kind!r} declares no free-text bound, so {key!r} at {size} bytes would be "
                f"stored unbounded: declare {kind!r} in KIND_TEXT_BYTES"
            )


def _prepare_entry(
    key: str, value: object, redact: Callable[[str], str] | None, cut_at: int | None
) -> dict[str, object]:

    if key in TRUNCATABLE_KEYS and isinstance(value, (dict, list)):
        raise InvalidEventError(
            f"payload key {key!r} is capped free text and must be a string, "
            f"got {type(value).__name__}"
        )
    prepared = _redacted(value, redact)
    if cut_at is None or key in FOLD_READ_KEYS or not isinstance(prepared, str):
        return {key: prepared}
    cut, original = _truncate(prepared, cut_at)
    if cut == prepared:
        return {key: prepared}
    return {
        key: cut,
        f"{key}_truncated": True,
        f"{key}_original_length_bytes": original,
    }


def prepare_payload(
    payload: Mapping[str, object],
    *,
    kind: str | None = None,
    redact: Callable[[str], str] | None = None,
    max_text_bytes: int = MAX_TEXT_BYTES,
) -> dict[str, object]:

    cut_at, refuse_over = _text_bound(kind, max_text_bytes)
    prepared: dict[str, object] = {}
    for key, value in payload.items():
        prepared.update(_prepare_entry(key, value, redact, cut_at))
    if kind is not None and refuse_over is not None:
        _refuse_unbounded(kind, prepared, refuse_over)
    return prepared


def append_lines(path: Path, lines: Sequence[str]) -> None:

    needs_newline = False
    if path.exists():
        with path.open("rb") as stream:
            if stream.seek(0, os.SEEK_END):
                stream.seek(-1, os.SEEK_END)
                needs_newline = stream.read(1) != b"\n"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        if needs_newline:
            stream.write("\n")
        for line in lines:
            stream.write(line + "\n")


def append(  # noqa: PLR0913 — every keyword is an injected dependency the kit may not read
    directory: Path | str,
    drafts: Iterable[Draft],
    *,
    actor: str = "",
    clock: Callable[[], float] | None = None,
    redact: Callable[[str], str] | None = None,
    max_text_bytes: int = MAX_TEXT_BYTES,
    held_lock: LedgerLock | None = None,
    lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
    writer: str | None = None,
) -> list[Event]:

    pending = list(drafts)
    if not pending:
        return []
    for draft in pending:
        ids.validate_record_id(draft.record)  # type: ignore[attr-defined]
        if not KIND_PATTERN.match(draft.kind):
            raise InvalidEventError(f"kind {draft.kind!r} must match {KIND_PATTERN.pattern}")
    ledger = Path(directory)
    ledger.mkdir(parents=True, exist_ok=True)
    now = time.time if clock is None else clock
    lock = held_lock if held_lock is not None else LedgerLock(ledger, timeout_s=lock_timeout_s)
    acquired = held_lock is None
    if acquired:
        lock.acquire()
    try:
        existing, _ = read_events(ledger)
        state = fold(existing)
        seen = {event.id for event in existing}
        minted: list[Event] = []
        for draft in pending:
            payload = prepare_payload(
                draft.payload, kind=draft.kind, redact=redact, max_text_bytes=max_text_bytes
            )
            event_id = event_id_for(draft.record, draft.kind, payload, generation=draft.generation)
            if event_id in seen:
                continue
            item = state.records.setdefault(draft.record, RecordState(record=draft.record))
            item.totals = accumulate(item.totals, draft.kind, payload)
            handler = _HANDLERS.get(draft.kind)
            if handler is not None:
                handler(item, payload)
            item.max_seq += 1
            minted.append(
                Event(
                    id=event_id,
                    record=draft.record,
                    seq=item.max_seq,
                    kind=draft.kind,
                    actor=draft.actor or actor or UNATTRIBUTED_ACTOR,
                    ts=_stamp(now()),
                    payload=payload,
                    totals=item.totals,
                )
            )
            seen.add(event_id)
        if minted:
            append_lines(append_target(ledger, writer=writer), [to_json(event) for event in minted])
        return minted
    finally:
        if acquired:
            lock.release()


def _withdrawn_payload(event: Event) -> dict[str, object]:

    payload: dict[str, object] = {WITHDRAWN_FROM: event.id}
    for key, value in event.payload.items():
        if key in FOLD_READ_KEYS:
            payload[key] = value
            continue
        payload[key] = WITHDRAWN_PLACEHOLDER
        payload[key + WITHDRAWN_SUFFIX] = True
    return payload


def _find_line(ledger: Path, event_id: str) -> tuple[Path, str, int, Event]:

    for path in ledger_paths(ledger):
        text = path.read_text(encoding="utf-8")
        for index, line in enumerate(text.splitlines()):
            try:
                event = from_json(line)
            except InvalidEventError:
                continue
            if event.id == event_id:
                return path, text, index, event
    raise InvalidEventError(f"no event in the log carries the id {event_id!r}")


def _publish_text(path: Path, text: str) -> None:

    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def withdraw(  # noqa: PLR0913 - `append`'s injected seams, plus which event and why
    directory: Path | str,
    event_id: str,
    *,
    reason: str,
    actor: str = "",
    clock: Callable[[], float] | None = None,
    redact: Callable[[str], str] | None = None,
    lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
) -> Event:

    ledger = Path(directory)
    with LedgerLock(ledger, timeout_s=lock_timeout_s) as lock:
        path, text, index, target = _find_line(ledger, event_id)
        if target.kind == KIND_WITHDRAWN:
            raise InvalidEventError(
                f"{event_id} is the {KIND_WITHDRAWN} trail of another withdrawal, and "
                f"withdrawing that would leave the first one unaccounted for"
            )
        if WITHDRAWN_FROM in target.payload:
            raise InvalidEventError(f"{event_id} has already been withdrawn")
        payload = _withdrawn_payload(target)
        if len(payload) == len(target.payload) + 1:
            raise InvalidEventError(
                f"every key on {event_id} is one the fold reads by name, so there is no free "
                f"text to withdraw and the trail would claim a removal that removed nothing"
            )
        minted = event_id_for(target.record, target.kind, payload)
        stored, _ = read_events(ledger)
        if any(event.id == minted for event in stored):
            raise InvalidEventError(
                f"withdrawing {event_id} would mint {minted}, which the log already holds"
            )
        lines = text.splitlines()
        lines[index] = to_json(replace(target, id=minted, payload=payload))
        _publish_text(path, "\n".join(lines) + ("\n" if text.endswith("\n") else ""))
        recorded = append(
            ledger,
            [
                Draft(
                    target.record,
                    KIND_WITHDRAWN,
                    {WITHDRAWN_TARGET: minted, WITHDRAWN_REASON: reason},
                )
            ],
            actor=actor,
            clock=clock,
            redact=redact,
            held_lock=lock,
        )
        return recorded[0]
