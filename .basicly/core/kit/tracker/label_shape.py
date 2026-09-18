from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside label_shape.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


events = _load("events.py", "basicly_tracker_kit_events")

LABELS_FIELD = "labels"
LABEL_SEPARATOR = ","

KIND_CREATED = events.KIND_CREATED
KIND_FIELD = events.KIND_FIELD

MAX_SPLIT_LABEL_CHARS = 1


def labels_of(value: object) -> tuple:

    if isinstance(value, str):
        return tuple(part for part in (raw.strip() for raw in value.split(LABEL_SEPARATOR)) if part)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def labels_written_by(event: Any) -> tuple:

    payload = event.payload
    if not isinstance(payload, dict):
        return ()
    if event.kind == KIND_CREATED:
        return labels_of(payload.get(LABELS_FIELD))
    if event.kind == KIND_FIELD and payload.get("name") == LABELS_FIELD:
        return labels_of(payload.get("value"))
    return ()


def split_labels(ordered: Any) -> tuple:

    found: dict = {}
    for event in ordered:
        offending = {
            label for label in labels_written_by(event) if len(label) <= MAX_SPLIT_LABEL_CHARS
        }
        if offending:
            labels, ids = found.setdefault(event.record, (set(), set()))
            labels |= offending
            ids.add(event.id)
    return tuple(
        (record, tuple(sorted(labels)), tuple(sorted(ids)))
        for record, (labels, ids) in sorted(found.items())
    )
