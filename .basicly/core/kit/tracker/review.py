from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside review.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


events = _load("events.py", "basicly_tracker_kit_events")
shaping = _load("shaping.py", "basicly_tracker_kit_shaping")
label_shape = _load("label_shape.py", "basicly_tracker_kit_label_shape")
writers = _load("writers.py", "basicly_tracker_kit_writers")

REVIEW_LABEL = shaping.REFINE_LABEL
IN_PROGRESS = "in_progress"


class UnreviewedError(events.LedgerError):
    pass


def _after(state: Any, drafts: Sequence[Any], record: str) -> dict[str, object]:

    fields = dict(state.fields) if state is not None else {}
    for draft in drafts:
        if draft.record == record and draft.kind == events.KIND_FIELD:
            fields[str(draft.payload.get("name"))] = draft.payload.get("value")
    return fields


def _labels(fields: Mapping[str, object]) -> set:
    return set(label_shape.labels_of(fields.get(label_shape.LABELS_FIELD)))


def _starts(drafts: Sequence[Any], record: str) -> bool:
    return any(
        draft.record == record
        and draft.kind == events.KIND_STATUS
        and draft.payload.get("status") == IN_PROGRESS
        for draft in drafts
    )


def refuse(states: Mapping[str, Any], drafts: Sequence[Any], writer: str, template=None) -> None:

    for record in sorted({draft.record for draft in drafts}):
        state = states.get(record)
        before = _labels(state.fields) if state is not None else set()
        fields = _after(state, drafts, record)
        marked = REVIEW_LABEL in _labels(fields)
        owed = shaping.refused(fields, template=template)
        if REVIEW_LABEL in before and not marked:
            if not writer.startswith(writers.AGENT):
                raise UnreviewedError(
                    f"{record} waits for an agent review: only an agent removes the "
                    f"{REVIEW_LABEL} label, after it fills the missing detail"
                )
            if owed:
                raise UnreviewedError(
                    f"{record} still owes {', '.join(owed)}, so the review is not done; fill "
                    f"them in the same update that removes {REVIEW_LABEL}"
                )
        if _starts(drafts, record) and shaping.held_from_ready(
            fields, labelled=marked, template=template
        ):
            why = f"it waits for an agent review ({REVIEW_LABEL})" if marked else "it owes "
            why += "" if marked else ", ".join(owed)
            raise UnreviewedError(
                f"{record} cannot start: {why}; an agent reviews it and fills the missing "
                f"detail first"
            )
