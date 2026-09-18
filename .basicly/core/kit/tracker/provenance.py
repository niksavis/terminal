from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable
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
        raise ImportError("the tracker kit's events.py is missing from beside provenance.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[EVENTS_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


events = _load_events()

_LABELS_MODULE_NAME = "basicly_tracker_kit_labels"


def _load_labels() -> Any:

    cached = sys.modules.get(_LABELS_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_LABELS_MODULE_NAME, _HERE / "labels.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("the tracker kit's labels.py is missing from beside provenance.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_LABELS_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


labels = _load_labels()

InvalidEdgeError = labels.InvalidEdgeError
KIND_EDGE = events.KIND_EDGE
EXTRACTED = labels.EXTRACTED
INFERRED = labels.INFERRED
AMBIGUOUS = labels.AMBIGUOUS
LABELS = labels.LABELS
WRITER_LABELS = labels.WRITER_LABELS
DISPOSITION_GATE = labels.DISPOSITION_GATE
DISPOSITION_PROPOSE = labels.DISPOSITION_PROPOSE
DISPOSITION_DECIDE = labels.DISPOSITION_DECIDE
DECISION_KIND = labels.DECISION_KIND
KEY_TARGET = labels.KEY_TARGET
KEY_TYPE = labels.KEY_TYPE
KEY_LABEL = labels.KEY_LABEL
KEY_DETAIL = labels.KEY_DETAIL
ALT_KEY_TARGET = labels.ALT_KEY_TARGET
ALT_KEY_TYPE = labels.ALT_KEY_TYPE
DIALECT_DECLARED = labels.DIALECT_DECLARED
DIALECT_ENGINE = labels.DIALECT_ENGINE
EDGE_TYPE_PATTERN = labels.EDGE_TYPE_PATTERN
strength_of = labels.strength_of
disposition = labels.disposition
validate_label = labels.validate_label
validate_edge_type = labels.validate_edge_type
edge_dialect = labels.edge_dialect


@dataclass(frozen=True, order=True)
class EdgeKey:
    source: str
    edge_type: str
    target: str

    def as_text(self) -> str:
        return f"{self.source} -[{self.edge_type}]-> {self.target}"


@dataclass(frozen=True)
class EdgeAssertion:
    key: EdgeKey
    label: str
    event_id: str
    seq: int
    actor: str
    detail: str


@dataclass(frozen=True)
class MalformedEdge:
    event_id: str
    record: str
    reason: str


@dataclass
class EdgeState:
    key: EdgeKey
    history: list[EdgeAssertion]

    @property
    def label(self) -> str:

        best = self.history[0]
        for assertion in self.history[1:]:
            if strength_of(assertion.label) >= strength_of(best.label):
                best = assertion
        return best.label

    @property
    def disposition(self) -> str:
        return disposition(self.label)

    @property
    def gates(self) -> bool:

        return self.disposition == DISPOSITION_GATE

    @property
    def proposal(self) -> bool:
        return self.disposition == DISPOSITION_PROPOSE

    @property
    def needs_decision(self) -> bool:
        return self.disposition == DISPOSITION_DECIDE


@dataclass
class EdgeFold:
    edges: dict[EdgeKey, EdgeState] = field(default_factory=dict)
    unknown_labels: dict[str, int] = field(default_factory=dict)
    writer_labels: dict[str, int] = field(default_factory=dict)
    malformed: list[MalformedEdge] = field(default_factory=list)
    dialects: dict[str, int] = field(default_factory=dict)


def edge_draft(
    key: EdgeKey,
    label: str,
    *,
    detail: str = "",
    actor: str = "",
    generation: int = 1,
) -> Any:

    validate_label(label)
    validate_edge_type(key.edge_type)
    for record in (key.source, key.target):
        try:
            events.ids.validate_record_id(record)
        except events.ids.IdError as exc:
            raise InvalidEdgeError(f"edge {key.as_text()}: {exc}") from exc
    if key.source == key.target:
        raise InvalidEdgeError(f"edge {key.as_text()} points a record at itself")
    return events.Draft(
        record=key.source,
        kind=KIND_EDGE,
        payload={
            KEY_TARGET: key.target,
            KEY_TYPE: key.edge_type,
            KEY_LABEL: label,
            KEY_DETAIL: detail,
        },
        actor=actor,
        generation=generation,
    )


def confirmation_draft(key: EdgeKey, *, detail: str = "", actor: str = "") -> Any:

    return edge_draft(key, EXTRACTED, detail=detail, actor=actor)


def is_edge_event(event: Any) -> bool:

    return event.kind == KIND_EDGE


def _required_text(payload: Any, key: str) -> str:

    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise InvalidEdgeError(
            f"an {KIND_EDGE} event needs a non-empty string {key}, got {value!r}"
        )
    return value


def read_assertion(event: Any) -> EdgeAssertion:

    if not is_edge_event(event):
        raise InvalidEdgeError(f"event {event.id} is kind {event.kind!r}, not {KIND_EDGE!r}")
    payload = event.payload
    target_key, type_key = labels.DIALECT_KEYS[edge_dialect(payload)]
    key = EdgeKey(
        source=event.record,
        edge_type=_required_text(payload, type_key),
        target=_required_text(payload, target_key),
    )
    detail = payload.get(KEY_DETAIL, "")
    if not isinstance(detail, str):
        raise InvalidEdgeError(f"an {KIND_EDGE} event needs string {KEY_DETAIL}, got {detail!r}")
    return EdgeAssertion(
        key=key,
        label=_required_text(payload, KEY_LABEL),
        event_id=event.id,
        seq=event.seq,
        actor=event.actor,
        detail=detail,
    )


def fold_edges(collected: Iterable[Any]) -> EdgeFold:

    result = EdgeFold()
    for event in events.canonical_order(collected):
        if not is_edge_event(event):
            continue
        dialect = edge_dialect(event.payload)
        try:
            assertion = read_assertion(event)
        except InvalidEdgeError as exc:
            result.malformed.append(MalformedEdge(event.id, event.record, str(exc)))
            continue
        result.dialects[dialect] = result.dialects.get(dialect, 0) + 1
        if assertion.label in WRITER_LABELS:
            count = result.writer_labels.get(assertion.label, 0)
            result.writer_labels[assertion.label] = count + 1
        elif assertion.label not in LABELS:
            count = result.unknown_labels.get(assertion.label, 0)
            result.unknown_labels[assertion.label] = count + 1
        state = result.edges.get(assertion.key)
        if state is None:
            result.edges[assertion.key] = EdgeState(key=assertion.key, history=[assertion])
        else:
            state.history.append(assertion)
    return result


def edges_by_disposition(
    edge_fold: EdgeFold, wanted: str, *, source: str | None = None
) -> tuple[EdgeState, ...]:

    return tuple(
        edge_fold.edges[key]
        for key in sorted(edge_fold.edges)
        if edge_fold.edges[key].disposition == wanted and (source is None or key.source == source)
    )


def gating_edges(edge_fold: EdgeFold, source: str | None = None) -> tuple[EdgeState, ...]:

    return edges_by_disposition(edge_fold, DISPOSITION_GATE, source=source)


@dataclass(frozen=True)
class EdgeDecision:
    record: str
    kind: str
    question: str
    detail: str
    key: EdgeKey


def _history_detail(state: EdgeState) -> str:

    return "\n".join(
        f"seq {assertion.seq}: {assertion.label}"
        f" by {assertion.actor or '<unattributed>'}"
        f"{' — ' + assertion.detail if assertion.detail else ''}"
        for assertion in state.history
    )


def decision_requests(edge_fold: EdgeFold) -> tuple[EdgeDecision, ...]:

    return tuple(
        EdgeDecision(
            record=state.key.source,
            kind=DECISION_KIND,
            question=f"Does the edge {state.key.as_text()} hold?",
            detail=_history_detail(state),
            key=state.key,
        )
        for state in edges_by_disposition(edge_fold, DISPOSITION_DECIDE)
    )
