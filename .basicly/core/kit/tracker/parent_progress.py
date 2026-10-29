from __future__ import annotations

import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's " + file_name + " is missing from beside commands.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


queries = _load("queries.py", "basicly_tracker_kit_queries")
differential = queries.differential
events = differential.events


def progress(found: Sequence[Any], drafts: Sequence[Any]) -> tuple[list[Any], set[str]]:
    views = differential.views_from_events(found)
    children = differential.children_of(views, differential.DEFAULT_VOCABULARY)
    statuses = {record: view.status for record, view in views.items() if not view.tombstoned}
    explicit = set()
    for draft in drafts:
        if draft.kind == events.KIND_STATUS:
            statuses[draft.record] = draft.payload.get("status")
            explicit.add(draft.record)
    active = {record for record, status in statuses.items() if status == "in_progress"}
    parents = set()
    while True:
        added = {
            parent
            for parent, descendants in children.items()
            if statuses.get(parent) in ("open", "in_progress")
            and any(child in active for child in descendants)
        } - parents
        if not added:
            break
        parents.update(added)
        active.update(added)
    affected = {draft.record for draft in drafts}
    result = list(drafts)
    pending = set(parents)
    while True:
        reached = {
            parent
            for parent in pending
            if parent in affected
            or any(child in affected and child in active for child in children[parent])
        }
        if not reached:
            break
        result.extend(
            events.Draft(parent, events.KIND_STATUS, {"status": "in_progress"})
            for parent in sorted(reached)
            if statuses[parent] == "open" and parent not in explicit
        )
        affected.update(reached)
        pending.difference_update(reached)
    return result, parents
