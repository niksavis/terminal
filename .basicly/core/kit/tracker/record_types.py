from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside record_types.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


events = _load("events.py", "basicly_tracker_kit_events")

TYPE_FIELD = "issue_type"
PARENT_CHILD = "parent-child"
EDGE_FROM, EDGE_TO, EDGE_TYPE = "from", "to", "type"
RECORD_TYPES = ("task", "bug", "feature", "chore", "epic", "research")
CHILD_TYPES: Mapping[str, tuple[str, ...]] = {
    "epic": ("feature", "task", "bug", "chore", "research"),
    "feature": ("task", "bug", "chore"),
}


class RefusedTypeError(events.LedgerError):
    pass


def type_of(fields: Mapping[str, object]) -> str:

    value = fields.get(TYPE_FIELD)
    return value if isinstance(value, str) else ""


def parents_for(child_type: str) -> tuple[str, ...]:
    return tuple(parent for parent, children in CHILD_TYPES.items() if child_type in children)


def refuse_type(value: object) -> None:

    if value in RECORD_TYPES:
        return
    raise RefusedTypeError(f"{value!r} is not a record type; use one of {', '.join(RECORD_TYPES)}")


def _a(kind: str) -> str:
    return f"an {kind}" if kind[:1] in "aeiou" else f"a {kind}"


def refuse_parent(parent: str, parent_type: str, child: str, child_type: str) -> None:

    if not parent_type or not child_type:
        return
    if child_type in CHILD_TYPES.get(parent_type, ()):
        return
    allowed = parents_for(child_type)
    remedy = (
        f"{_a(child_type)} may sit under {' or '.join(_a(kind) for kind in allowed)}"
        if allowed
        else f"{_a(child_type)} sits under no record"
    )
    raise RefusedTypeError(
        f"{child} is {_a(child_type)} and {parent} is {_a(parent_type)}, and "
        f"{_a(parent_type)} holds no {child_type}; {remedy}"
    )


def _parent_edges(found: Iterable[Any]) -> list[tuple[str, str]]:
    return [
        (event.payload.get(EDGE_FROM), event.payload.get(EDGE_TO))
        for event in found
        if event.kind == events.KIND_EDGE and event.payload.get(EDGE_TYPE) == PARENT_CHILD
    ]


def refuse_drafts(states: Mapping[str, Any], drafts: Sequence[Any], found: Iterable[Any]) -> None:

    types = {key: type_of(state.fields) for key, state in states.items()}
    retyped: set[str] = set()
    links: list[tuple[str, str]] = []
    for draft in drafts:
        payload = draft.payload
        if draft.kind == events.KIND_CREATED and TYPE_FIELD in payload:
            refuse_type(payload[TYPE_FIELD])
            types[draft.record] = str(payload[TYPE_FIELD])
        elif draft.kind == events.KIND_FIELD and payload.get("name") == TYPE_FIELD:
            refuse_type(payload.get("value"))
            types[draft.record] = str(payload.get("value"))
            retyped.add(draft.record)
        elif draft.kind == events.KIND_EDGE and payload.get(EDGE_TYPE) == PARENT_CHILD:
            links.append((payload.get(EDGE_FROM), payload.get(EDGE_TO)))
    if retyped:
        links += [edge for edge in _parent_edges(found) if retyped & set(edge)]
    for child, parent in links:
        refuse_parent(parent, types.get(parent, ""), child, types.get(child, ""))
