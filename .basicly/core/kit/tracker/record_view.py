from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's " + file_name + " is missing from beside it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


queries = _load("queries.py", "basicly_tracker_kit_queries")
shaping = _load("shaping.py", "basicly_tracker_kit_shaping")
templates = _load("templates.py", "basicly_tracker_kit_templates")
label_shape = _load("label_shape.py", "basicly_tracker_kit_label_shape")
forks = _load("forks.py", "basicly_tracker_kit_forks")
process = _load("process_evidence.py", "basicly_tracker_kit_process_evidence")
snapshot = queries.snapshot
events = snapshot.events

REFINE_LABEL = shaping.REFINE_LABEL


def is_closed(state: Any) -> bool:
    vocabulary = queries.differential.DEFAULT_VOCABULARY
    return bool(state.tombstoned) or state.status in vocabulary.closed_statuses


def owed_of(directory: Path | str, record: str) -> dict[str, object]:

    return _owed(events.read_events(directory)[0], record, templates.load(directory))


def _owed(found: list[Any], record: str, template: Any) -> dict[str, object]:
    state = events.fold(found).records.get(record)
    held = dict(state.fields) if state is not None else {}
    closed = state is not None and is_closed(state)
    debt = () if closed else process.readiness(found, record, held, template=template)
    missing = shaping.owed(held, closed=closed, template=template, process=debt)
    blocking = shaping.refused(held, closed=closed, template=template, process=debt)
    remedy = shaping.remedy(blocking) if blocking else ""
    note = process.review_note(found, record, held, template=template) if debt else ""
    if note and note != process.NO_REVIEW:
        remedy = f"{note}; {remedy}"
    return {"owed": list(missing), "blocking": list(blocking), "remedy": remedy}


def _title(states: Mapping[str, Any], record: str) -> str:
    return str(states[record].fields.get("title", "")) if record in states else ""


def _edges(record: str, views: Mapping[str, Any], states: Mapping[str, Any]) -> dict[str, object]:

    view = views.get(record)
    return {
        "dependencies": [
            {
                "id": edge.target,
                "dependency_type": edge.type,
                "status": _status(views, edge.target),
                "title": _title(states, edge.target),
            }
            for edge in (view.dependencies if view is not None else ())
        ],
        "dependents": [
            {
                "id": other,
                "dependency_type": edge.type,
                "status": held.status or "",
                "title": _title(states, other),
            }
            for other, held in sorted(views.items())
            for edge in held.dependencies
            if edge.target == record and not held.tombstoned
        ],
    }


def _status(views: Mapping[str, Any], record: str) -> str:
    view = views.get(record)
    return "unknown" if view is None else view.status or ""


def read_record(directory: Path | str, record: str) -> dict[str, object] | None:

    states = queries.folded(directory)
    state = states.get(record)
    if state is None:
        return None
    found = events.read_events(directory)[0]
    template = templates.load(directory)
    views = queries.differential.views_from_events(found)
    shown = snapshot.record_to_dict(state)
    shown.update(_edges(record, views, states))
    now = queries.holders.newest(states)
    shown["holder"] = queries.holders.holding(state, template.stale_days, now)
    ordered = events.canonical_order(found)
    shown["conflicts"] = forks.of_record(ordered, record)
    shown["comment_log"] = [
        {
            "text": event.payload["text"],
            "writer": event.actor,
            "at": event.ts,
            "seq": event.seq,
            "id": event.id,
            **{
                key: event.payload[key]
                for key in ("text_truncated", "text_original_length_bytes")
                if key in event.payload
            },
        }
        for event in ordered
        if event.record == record
        and event.kind in events.PROSE_KINDS
        and isinstance(event.payload.get("text"), str)
    ]
    shown["process"] = process.confirmation_report(found, record, template=template)
    shown.update(_owed(found, record, template))
    return shown


def _handoff_key(note: Mapping[str, Any]) -> tuple[str, str] | None:
    text, writer = note.get("text"), note.get("writer")
    if not isinstance(text, str) or not isinstance(writer, str) or not writer:
        return None
    if text.startswith("[model handoff]"):
        return "model handoff", writer
    if re.match(r"^\[session handover \d{4}-\d{2}-\d{2}\]", text):
        return "session handover", writer
    return None


def source_loss(notes: list[dict[str, Any]]) -> list[dict[str, object]]:
    return [
        {
            "id": note["id"],
            "original_length_bytes": note.get("text_original_length_bytes"),
            "reason": (
                "Writer truncated this note; original content cannot be recovered from the ledger."
            ),
        }
        for note in notes
        if note.get("text_truncated") is True
    ]


def read_source_loss(directory: Path | str, record: str) -> list[dict[str, object]]:
    found, quarantined = events.read_events(directory)
    if quarantined:
        raise ValueError("repair unreadable ledger events before assembling recovery context")
    notes = [
        {"id": event.id, **event.payload}
        for event in found
        if event.record == record and event.kind in events.PROSE_KINDS
    ]
    return source_loss(notes)


def read_view(
    directory: Path | str,
    record: str,
    *,
    view: str = "full",
    snapshot: str | None = None,
) -> dict[str, object] | None:
    if view not in {"full", "current", "history"}:
        raise ValueError("unknown record view; use full, current or history")
    found = read_record(directory, record)
    if found is None:
        return None
    if view == "full" and snapshot is None:
        return found
    encoded = json.dumps(found, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    identity = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if snapshot is not None and snapshot != identity:
        raise ValueError(record + ": snapshot changed; read show --view current before retrieval")
    if view == "full":
        return found
    if view == "history":
        return {**found, "view": view, "snapshot_identity": identity}
    notes = cast("list[dict[str, Any]]", found["comment_log"])
    process_state = cast("dict[str, Any]", found["process"])
    latest = {key: note["seq"] for note in notes if (key := _handoff_key(note)) is not None}
    retained = [
        note for note in notes if (key := _handoff_key(note)) is None or latest[key] == note["seq"]
    ]
    current = {
        key: value
        for key, value in found.items()
        if key not in {"comments", "comment_log", "process"}
    }
    current.update({
        "view": view,
        "snapshot_identity": identity,
        "complete_contract": False,
        "source_loss": source_loss(notes),
        "notes": retained,
        "process": {
            key: value
            for key, value in process_state.items()
            if key in {"review_current", "confirmation_current", "revision", "owed"}
        },
        "history_reference": {
            "view": "history",
            "record": record,
            "snapshot": identity,
            "note_count": len(notes),
            "omitted_notes": len(notes) - len(retained),
        },
        "coverage_and_omissions": (
            "Current fields, artifacts, all ordinary clarification notes and the latest "
            "handoff per kind and writer. Older handoffs and process detail remain in "
            "snapshot-checked history. Handoffs are recovery guidance, not a complete "
            "contract; retrieve history for unresolved or conflicting facts."
        ),
    })
    return current


def scaffold_of(directory: Path | str, kind: str) -> dict[str, object]:
    return {"type": kind, **shaping.body(kind, templates.load(directory))}


def refine_queue(directory: Path | str) -> dict[str, object]:

    template = templates.load(directory)
    states = queries.folded(directory)
    found = events.read_events(directory)[0]
    now = queries.holders.newest(states)
    rows = []
    for record, state in sorted(states.items()):
        if is_closed(state):
            continue
        held = dict(state.fields)
        labelled = REFINE_LABEL in label_shape.labels_of(held.get(label_shape.LABELS_FIELD))
        blocking = shaping.refused(
            held,
            template=template,
            process=process.readiness(found, record, held, template=template),
        )
        if labelled or blocking:
            rows.append({
                "record": record,
                "title": str(held.get("title", "")),
                "labelled": labelled,
                "blocking": list(blocking),
                "holder": queries.holders.holding(state, template.stale_days, now),
            })
    return {"label": REFINE_LABEL, "count": len(rows), "records": rows}
