from __future__ import annotations

import importlib.util
import re
import sys
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


class InvalidEdgeError(events.InvalidEventError):
    pass


EXTRACTED = "EXTRACTED"
INFERRED = "INFERRED"
AMBIGUOUS = "AMBIGUOUS"

LABELS = (AMBIGUOUS, EXTRACTED, INFERRED)

WRITER_LABELS = frozenset({"engine", "dual-write"})

_STRENGTH = {AMBIGUOUS: 1, INFERRED: 2, EXTRACTED: 3} | dict.fromkeys(WRITER_LABELS, 3)

_UNKNOWN_STRENGTH = 0

DISPOSITION_GATE = "gate"
DISPOSITION_PROPOSE = "propose"
DISPOSITION_DECIDE = "decide"

_DISPOSITIONS = {
    EXTRACTED: DISPOSITION_GATE,
    INFERRED: DISPOSITION_PROPOSE,
    AMBIGUOUS: DISPOSITION_DECIDE,
} | dict.fromkeys(WRITER_LABELS, DISPOSITION_GATE)

KIND_EDGE = events.KIND_EDGE

KEY_TARGET = "target"
KEY_TYPE = "edge_type"
KEY_LABEL = "provenance"
KEY_DETAIL = "detail"

ALT_KEY_TARGET = "to"
ALT_KEY_TYPE = "type"

DIALECT_DECLARED = f"{KEY_TARGET}/{KEY_TYPE}"
DIALECT_ENGINE = f"{ALT_KEY_TARGET}/{ALT_KEY_TYPE}"

DIALECT_KEYS = {
    DIALECT_DECLARED: (KEY_TARGET, KEY_TYPE),
    DIALECT_ENGINE: (ALT_KEY_TARGET, ALT_KEY_TYPE),
}

EDGE_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

DECISION_KIND = "validate"


def strength_of(label: str) -> int:

    return _STRENGTH.get(label, _UNKNOWN_STRENGTH)


def disposition(label: str) -> str:

    return _DISPOSITIONS.get(label, DISPOSITION_DECIDE)


def validate_label(label: str) -> str:

    if label not in LABELS:
        raise InvalidEdgeError(f"provenance label {label!r} must be one of {LABELS}")
    return label


def validate_edge_type(edge_type: str) -> str:

    if not EDGE_TYPE_PATTERN.match(edge_type):
        raise InvalidEdgeError(f"edge type {edge_type!r} must match {EDGE_TYPE_PATTERN.pattern}")
    return edge_type


def _has_text(payload: Any, key: str) -> bool:
    value = payload.get(key)
    return isinstance(value, str) and bool(value)


def edge_dialect(payload: Any) -> str:

    declared = _has_text(payload, KEY_TARGET) and _has_text(payload, KEY_TYPE)
    engine = _has_text(payload, ALT_KEY_TARGET) and _has_text(payload, ALT_KEY_TYPE)
    return DIALECT_ENGINE if engine and not declared else DIALECT_DECLARED
