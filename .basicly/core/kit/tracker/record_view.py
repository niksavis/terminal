from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

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
snapshot = queries.snapshot
events = snapshot.events


def is_closed(state: Any) -> bool:
    vocabulary = queries.differential.DEFAULT_VOCABULARY
    return bool(state.tombstoned) or state.status in vocabulary.closed_statuses


def owed_of(directory: Path | str, record: str) -> dict[str, object]:

    found, _ = events.read_events(directory)
    state = events.fold(found).records.get(record)
    held = dict(state.fields) if state is not None else {}
    closed = state is not None and is_closed(state)
    missing = shaping.owed(held, closed=closed)
    blocking = shaping.refused(held, closed=closed)
    return {
        "owed": list(missing),
        "refused": list(blocking),
        "remedy": shaping.remedy(blocking) if blocking else "",
    }


def _edges(record: str, views: Mapping[str, Any], states: Mapping[str, Any]) -> dict[str, object]:

    view = views.get(record)
    return {
        "dependencies": [
            {
                "id": edge.target,
                "dependency_type": edge.type,
                "status": _status(views, edge.target),
            }
            for edge in (view.dependencies if view is not None else ())
        ],
        "dependents": [
            {
                "id": other,
                "dependency_type": edge.type,
                "status": held.status or "",
                "title": str(states[other].fields.get("title", "")) if other in states else "",
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
    views, _ = queries.views_and_children(directory)
    shown = snapshot.record_to_dict(state)
    shown.update(_edges(record, views, states))
    return shown
