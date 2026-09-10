r"""Gate results on the owned ledger: the ``gate`` kind, and the per-issue view of it.

The boundary is *what a gate result means* against `events.py`, which stores the event and
folds no state for it (§4.5) — the split `provenance.py` takes for the ``edge`` kind. The
loop asks *is this gate green* at every advance (basicly-vkh0.26).

The writer is the dual write, `basicly.mirror`, translating an accepted gate report;
no export holds a gate field, so `migrate.py` had nothing to import and this kind arrives
only from a live write (`differential.EXPORT_CANNOT_EXPRESS`).

**Fail closed, three times.** A gate with no result from a counting provider is not green.
An unreadable gate event is reported in :attr:`GateFold.malformed`, not skipped. A
gate-family kind that is not :data:`KIND_GATE` — a later ``gate_waived`` — is counted in
:attr:`GateFold.unknown_kinds` and named on :attr:`GateView.unreadable`, so a consumer tells
*no waiver* from *a waiver I cannot read*; `events.fold` counts it in the record's totals,
which stops an old reader reporting every later event as a disagreement.

**The payload keys are still duplicated.** `differential.py` spells them as the kind's first
reader and `basicly.mirror` writes through that copy; the spellings are asserted equal in
`tests/test_kit_tracker_gates.py`. The kind itself is no longer among them (basicly-vkh0.36).

Kit rules bind here in full — no basicly, no syntax newer than 3.9, one exception class per
handler (`.basicly/core/kit/README.md`).
"""

# comment-density-waiver: cohesion: 16 documented members over 1,424 tokens of code, so the share is
# set by the member count; the prose holds the fail-closed rules and the duplication against
# differential.py, which no statement here says. 537 tokens of repeated prose were cut first.

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- the sibling event log ----------------------------------------------------

_HERE = Path(__file__).resolve().parent
EVENTS_MODULE_NAME = "basicly_tracker_kit_events"


def _load_events() -> Any:
    """Load ``events.py`` from beside this file, under the kit's shared module name.

    Public name, and it is a contract: a second load mints a second
    :class:`events.InvalidEventError`, which every ``except`` on it stops matching.

    Raises:
        ImportError: ``events.py`` is not beside this file.
    """
    cached = sys.modules.get(EVENTS_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(EVENTS_MODULE_NAME, _HERE / "events.py")
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's events.py is missing from beside gates.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[EVENTS_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


events = _load_events()


class InvalidGateError(events.InvalidEventError):
    """A gate result that cannot be recorded, or a recorded one that cannot be read.

    Subclasses the log's own error, so one ``except events.LedgerError`` catches both.
    """


# --- the vocabulary -----------------------------------------------------------

# Permanent vocabulary: never reused, never redefined, only added to (§4.5). Spelled once, in
# `events.KNOWN_KINDS`; this is that name rather than a second one (basicly-vkh0.36).
KIND_GATE = events.KIND_GATE

# One spelling per field (R2), and these three are it.
GATE_NAME_KEY = "gate"
GATE_PROVIDER_KEY = "provider"
GATE_PASSED_KEY = "passed"

# :data:`KIND_GATE`, plus any later ``gate_<something>``. A kind outside the family belongs
# to another reader; one inside it that we do not model is a newer writer's.
GATE_KIND_PATTERN = re.compile(r"^gate(?:_[a-z0-9_]+)?$")


def is_gate_kind(kind: str) -> bool:
    """Whether *kind* belongs to the gate family, modelled here or not."""
    return bool(GATE_KIND_PATTERN.match(kind))


def is_gate_event(event: Any) -> bool:
    """Whether *event* is a gate result this version reads."""
    return event.kind == KIND_GATE


def validate_token(value: object, field_name: str) -> str:
    """*value* as a gate name or a provider.

    Only emptiness and whitespace are refused: a gate name is the consumer's own, so a shape
    rule would refuse a legitimate one, while a token holding a space keys two results that
    read alike.

    Raises:
        InvalidGateError: not a string, empty, or holding whitespace.
    """
    if not isinstance(value, str) or not value or value.split() != [value]:
        raise InvalidGateError(
            f"a {KIND_GATE} event needs a non-empty whitespace-free {field_name}, got {value!r}"
        )
    return value


# --- what one gate result is --------------------------------------------------


@dataclass(frozen=True)
class GateResult:
    """One recorded gate result: the issue, the gate, the verdict, who claimed it, when.

    Attributes:
        provider: Unauthenticated, so whose claim counts is the caller's vocabulary
            (:meth:`GateView.green`).
        ts: When the ledger recorded it. Evidence, never an ordering key (§9.5).
        event_id: What a reader follows the claim back to.
    """

    record: str
    gate: str
    provider: str
    passed: bool
    ts: str = ""
    event_id: str = ""


@dataclass(frozen=True)
class MalformedGate:
    """A gate event that could not be read, named rather than silently dropped."""

    event_id: str
    record: str
    reason: str


@dataclass(frozen=True)
class GateView:
    """One issue's gate results, and the questions the loop asks of them.

    Attributes:
        results: Its latest result per ``(gate, provider)`` pair, rather than one row per
            gate, in the ledger's own order.
        unreadable: Gate-family kinds on this issue this version does not model.
    """

    record: str
    results: tuple[GateResult, ...] = ()
    unreadable: tuple[str, ...] = ()

    def result(self, gate: str, *, providers: Collection[str]) -> GateResult | None:
        """*gate*'s latest result from a provider in *providers*, or ``None`` for none.

        Latest by ledger order, not by provider name: two counting providers that disagree
        is not a contest a name can settle.
        """
        found = None
        for candidate in self.results:
            if candidate.gate == gate and candidate.provider in providers:
                found = candidate
        return found

    def green(self, gate: str, *, providers: Collection[str]) -> bool:
        """Whether *gate* passed for a counting provider; empty *providers* greens nothing."""
        found = self.result(gate, providers=providers)
        return found is not None and found.passed

    def required_green(
        self, required: Sequence[str], *, providers: Collection[str]
    ) -> dict[str, bool]:
        """Whether each gate in *required* is green, one entry per required gate."""
        return {gate: self.green(gate, providers=providers) for gate in required}


@dataclass
class GateFold:
    """The gate fold's output, including what it could not read.

    Attributes:
        views: Issue id to view, for the issues the log names.
        unknown_kinds: Gate-family kind to count, for a kind this version does not model.
        malformed: Gate events that could not be read at all.
    """

    views: dict[str, GateView] = field(default_factory=dict)
    unknown_kinds: dict[str, int] = field(default_factory=dict)
    malformed: list[MalformedGate] = field(default_factory=list)

    def view(self, record: str) -> GateView:
        """*record*'s view, empty when no gate event ever named it.

        Empty rather than ``KeyError``: no gate reported yet is the ordinary state, and
        :meth:`GateView.green` answers False for it.
        """
        return self.views.get(record, GateView(record=record))


# --- writing a result ---------------------------------------------------------


def gate_draft(record: str, gate: str, *, provider: str, passed: bool, generation: int = 1) -> Any:
    """A draft recording *gate*'s verdict on *record*, for `events.append`.

    Pure, so the caller keeps the lock scope and the batching, and everything refusable is
    refused before anything is authoritative. The actor is `events.append`'s: a gate result
    is recorded by whoever is appending, so there is nothing per-draft to say.

    Pass ``generation`` above 1 for a genuine re-run: an event id is content-derived, so a
    second identical verdict is otherwise swallowed as a replay — right for a replayed
    write, wrong for a gate that really ran twice and passed twice.

    Raises:
        InvalidGateError: the record id, gate name, provider or verdict cannot be recorded.
    """
    try:
        events.ids.validate_record_id(record)
    except events.ids.IdError as exc:
        raise InvalidGateError(f"{KIND_GATE} result on {record!r}: {exc}") from exc
    if not isinstance(passed, bool):
        raise InvalidGateError(f"a {KIND_GATE} event needs a boolean verdict, got {passed!r}")
    return events.Draft(
        record=record,
        kind=KIND_GATE,
        payload={
            GATE_NAME_KEY: validate_token(gate, GATE_NAME_KEY),
            GATE_PROVIDER_KEY: validate_token(provider, GATE_PROVIDER_KEY),
            GATE_PASSED_KEY: passed,
        },
        generation=generation,
    )


# --- reading results back -----------------------------------------------------


def read_result(event: Any) -> GateResult:
    """The result one gate event carries.

    Raises:
        InvalidGateError: not a gate event, or its payload is missing a structural field.
            The verdict must be a real boolean, or the string ``"false"`` reads as green.
    """
    if not is_gate_event(event):
        raise InvalidGateError(f"event {event.id} is kind {event.kind!r}, not {KIND_GATE!r}")
    passed = event.payload.get(GATE_PASSED_KEY)
    if not isinstance(passed, bool):
        raise InvalidGateError(
            f"a {KIND_GATE} event needs a boolean {GATE_PASSED_KEY}, got {passed!r}"
        )
    return GateResult(
        record=event.record,
        gate=validate_token(event.payload.get(GATE_NAME_KEY), GATE_NAME_KEY),
        provider=validate_token(event.payload.get(GATE_PROVIDER_KEY), GATE_PROVIDER_KEY),
        passed=passed,
        ts=event.ts,
        event_id=event.id,
    )


def fold_gates(collected: Iterable[Any]) -> GateFold:
    """Fold *collected* events into a per-issue gate view, in canonical order.

    Non-gate events are ignored, so a caller hands this whatever `events.read_events`
    returned, duplicates included. The order is `events.canonical_order`'s: the view is a
    function of the event **set**, so a shuffled log folds the same.
    """
    result = GateFold()
    latest: dict[str, dict[tuple[str, str], GateResult]] = {}
    unreadable: dict[str, list[str]] = {}
    for event in events.canonical_order(collected):
        if not is_gate_kind(event.kind):
            continue
        if not is_gate_event(event):
            result.unknown_kinds[event.kind] = result.unknown_kinds.get(event.kind, 0) + 1
            unreadable.setdefault(event.record, []).append(event.kind)
            continue
        try:
            found = read_result(event)
        except InvalidGateError as exc:
            result.malformed.append(MalformedGate(event.id, event.record, str(exc)))
            continue
        latest.setdefault(found.record, {})[(found.gate, found.provider)] = found
    for record in sorted(set(latest) | set(unreadable)):
        result.views[record] = GateView(
            record=record,
            results=tuple(latest.get(record, {}).values()),
            unreadable=tuple(unreadable.get(record, ())),
        )
    return result
