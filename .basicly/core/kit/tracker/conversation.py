from __future__ import annotations

import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    key = "basicly_tracker_kit_" + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, _HERE / (name + ".py"))
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's " + name + ".py is missing from beside it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


events = _load("events")
_text = _load("evidence_checks").filled_text


def fault(found: Sequence[Any], record: str, references: object) -> str:
    if not isinstance(references, list) or not references:
        return "it needs a list of at least one same-card comment seq"
    if len(set(map(repr, references))) != len(references):
        return "it lists a comment seq twice"
    return next(
        (reason for one in references if (reason := _reference_fault(found, record, one))), ""
    )


def _reference_fault(found: Sequence[Any], record: str, reference: object) -> str:
    if not isinstance(reference, int) or isinstance(reference, bool) or reference <= 0:
        return f"{reference!r} is not a comment seq"
    matching = [
        event
        for event in events.canonical_order(found)
        if event.record == record and event.seq == reference
    ]
    if len(matching) != 1:
        return f"comment {reference} " + (
            "has forked copies" if matching else f"is not on {record}"
        )
    if matching[0].kind not in events.PROSE_KINDS:
        return f"seq {reference} is a {matching[0].kind} event, not a comment"
    if not _text(matching[0].payload.get("text")):
        return (
            f"comment {reference} reads as an unfilled placeholder, because text in angle "
            "brackets counts as one; add a comment without it, or with it in backticks, "
            "and cite that seq"
        )
    return ""
