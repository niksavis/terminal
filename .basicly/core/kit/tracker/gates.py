from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
EVENTS_MODULE_NAME = "basicly_tracker_kit_events"


def _load_events() -> Any:

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
    pass


KIND_GATE = events.KIND_GATE

GATE_NAME_KEY = "gate"
GATE_PROVIDER_KEY = "provider"
GATE_PASSED_KEY = "passed"

GATE_KIND_PATTERN = re.compile(r"^gate(?:_[a-z0-9_]+)?$")


def is_gate_kind(kind: str) -> bool:
    return bool(GATE_KIND_PATTERN.match(kind))


def is_gate_event(event: Any) -> bool:
    return event.kind == KIND_GATE


def validate_token(value: object, field_name: str) -> str:

    if not isinstance(value, str) or not value or value.split() != [value]:
        raise InvalidGateError(
            f"a {KIND_GATE} event needs a non-empty whitespace-free {field_name}, got {value!r}"
        )
    return value


@dataclass(frozen=True)
class GateResult:
    record: str
    gate: str
    provider: str
    passed: bool
    ts: str = ""
    event_id: str = ""


@dataclass(frozen=True)
class MalformedGate:
    event_id: str
    record: str
    reason: str


@dataclass(frozen=True)
class GateView:
    record: str
    results: tuple[GateResult, ...] = ()
    unreadable: tuple[str, ...] = ()

    def result(self, gate: str, *, providers: Collection[str]) -> GateResult | None:

        found = None
        for candidate in self.results:
            if candidate.gate == gate and candidate.provider in providers:
                found = candidate
        return found

    def green(self, gate: str, *, providers: Collection[str]) -> bool:
        found = self.result(gate, providers=providers)
        return found is not None and found.passed

    def required_green(
        self, required: Sequence[str], *, providers: Collection[str]
    ) -> dict[str, bool]:
        return {gate: self.green(gate, providers=providers) for gate in required}


@dataclass
class GateFold:
    views: dict[str, GateView] = field(default_factory=dict)
    unknown_kinds: dict[str, int] = field(default_factory=dict)
    malformed: list[MalformedGate] = field(default_factory=list)

    def view(self, record: str) -> GateView:

        return self.views.get(record, GateView(record=record))


def gate_draft(record: str, gate: str, *, provider: str, passed: bool, generation: int = 1) -> Any:

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


def read_result(event: Any) -> GateResult:

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
