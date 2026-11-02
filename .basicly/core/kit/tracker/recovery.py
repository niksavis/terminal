from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _events() -> Any:
    name = "basicly_tracker_kit_events"
    if name in sys.modules:
        return sys.modules[name]
    source = Path(__file__).with_name("events.py")
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's events.py is missing from beside recovery.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


events = _events()
LOSS_ARTIFACT = "sequence-loss"
ACKNOWLEDGED_LOSS = "acknowledged-sequence-loss"
INVALID_ACKNOWLEDGMENT = "invalid-loss-acknowledgment"
_BODY_KEYS = frozenset({
    "record",
    "missing_sequences",
    "reason",
    "evidence",
    "boundary_seq",
    "history_sha256",
})


@dataclass(frozen=True)
class Request:
    sequences: tuple[int, ...]
    reason: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Coverage:
    record: str
    sequences: tuple[int, ...]
    event_id: str
    detail: str
    invalid: bool = False


def sequence_gaps(ordered: Iterable[Any]) -> dict[str, tuple[int, ...]]:
    seen: dict[str, set[int]] = {}
    for event in ordered:
        seen.setdefault(event.record, set()).add(event.seq)
    return {
        record: missing
        for record, claimed in seen.items()
        if (missing := tuple(sorted(set(range(1, max(claimed) + 1)) - claimed)))
    }


def history_digest(history: Sequence[Any]) -> str:
    text = "\n".join(events.to_json(one) for one in events.canonical_order(history))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _request(sequences: object, reason: object, evidence: object) -> Request:
    if (
        not isinstance(sequences, (list, tuple))
        or not sequences
        or any(type(one) is not int or one < 1 for one in sequences)
        or list(sequences) != sorted(set(sequences))
    ):
        raise events.InvalidEventError(
            "missing sequences must be distinct positive integers in order"
        )
    if not isinstance(reason, str) or not reason.strip():
        raise events.InvalidEventError("a loss acknowledgment needs a nonempty reason")
    if (
        not isinstance(evidence, (list, tuple))
        or not evidence
        or any(not isinstance(one, str) or not one.strip() for one in evidence)
    ):
        raise events.InvalidEventError("a loss acknowledgment needs historical evidence references")
    return Request(tuple(sequences), reason, tuple(evidence))


def _coverage(event: Any, ordered: Sequence[Any]) -> Coverage:
    body = event.payload.get("body")
    if not isinstance(body, Mapping) or set(body) != _BODY_KEYS:
        raise events.InvalidEventError("a loss acknowledgment has malformed body fields")
    if body["record"] != event.record:
        raise events.InvalidEventError("a loss acknowledgment names another record")
    request = _request(body["missing_sequences"], body["reason"], body["evidence"])
    boundary = body["boundary_seq"]
    if type(boundary) is not int or boundary < 1 or boundary >= event.seq:
        raise events.InvalidEventError("the loss boundary must precede its acknowledgment")
    history = [one for one in ordered if one.record == event.record and one.seq <= boundary]
    if not history or max(one.seq for one in history) != boundary:
        raise events.InvalidEventError("the acknowledged boundary no longer exists")
    if sequence_gaps(history).get(event.record, ()) != request.sequences:
        raise events.InvalidEventError(
            "the historical gaps differ from the acknowledged sequence set"
        )
    if history_digest(history) != body["history_sha256"]:
        raise events.InvalidEventError("the surviving history differs from its acknowledged digest")
    return Coverage(
        event.record,
        request.sequences,
        event.id,
        f"sequences {', '.join(map(str, request.sequences))} remain lost; "
        f"acknowledged at {event.ts}: {request.reason}; "
        f"historical evidence: {'; '.join(request.evidence)}; original content remains unknown",
    )


def assess(ordered: Sequence[Any]) -> tuple[Coverage, ...]:
    latest = {
        one.record: one
        for one in ordered
        if one.kind == events.KIND_ARTIFACT and one.payload.get("artifact") == LOSS_ARTIFACT
    }
    results = []
    for one in latest.values():
        try:
            results.append(_coverage(one, ordered))
        except events.InvalidEventError as exc:
            results.append(Coverage(one.record, (), one.id, str(exc), invalid=True))
    return tuple(results)


def acknowledge(
    directory: Path | str,
    record: str,
    request: Request,
    *,
    redact: Callable[[str], str] | None = None,
) -> list[Any]:
    request = _request(request.sequences, request.reason, request.evidence)
    ledger = Path(directory)
    with events.LedgerLock(ledger) as lock:
        found, quarantined = events.read_events(ledger)
        if quarantined:
            raise events.InvalidEventError(
                "repair unreadable ledger lines before acknowledging loss"
            )
        ordered = events.canonical_order(found)
        history = [one for one in ordered if one.record == record]
        if not any(one.kind == events.KIND_CREATED for one in history):
            raise events.InvalidEventError(f"the ledger holds no created record {record!r}")
        missing = sequence_gaps(history).get(record, ())
        if missing != request.sequences:
            raise events.InvalidEventError(
                f"{record}: current missing sequences are {list(missing)}, "
                f"not {list(request.sequences)}; inspect fsck and pass the exact sequence set"
            )
        body = {
            "record": record,
            "missing_sequences": list(request.sequences),
            "reason": request.reason,
            "evidence": list(request.evidence),
            "boundary_seq": max(one.seq for one in history),
            "history_sha256": history_digest(history),
        }
        return events.append(
            ledger,
            [events.Draft(record, events.KIND_ARTIFACT, {"artifact": LOSS_ARTIFACT, "body": body})],
            redact=redact,
            held_lock=lock,
        )
