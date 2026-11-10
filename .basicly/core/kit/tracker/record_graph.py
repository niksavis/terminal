from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
DEPTH = 8
LAST = 99


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


differential = _load("differential.py", "basicly_tracker_kit_differential")
VOCABULARY = differential.DEFAULT_VOCABULARY


def node(record: str, views: Mapping[str, Any], states: Mapping[str, Any]) -> dict[str, Any]:
    state = states.get(record)
    view = views.get(record)
    fields = state.fields if state is not None else {}
    return {
        "id": record,
        "title": str(fields.get("title") or ""),
        "status": "unknown" if view is None else view.status or "",
        "issue_type": str(fields.get("issue_type") or ""),
        "close_resolution": str(fields.get("close_resolution") or ""),
    }


def _parent(view: Any) -> str | None:
    return next(
        (edge.target for edge in view.dependencies if edge.type == VOCABULARY.parent_child_type),
        None,
    )


def _open(view: Any) -> bool:
    return not view.tombstoned and view.status not in VOCABULARY.closed_statuses


class Graph:
    def __init__(self, views: Mapping[str, Any], states: Mapping[str, Any]) -> None:
        self.views = views
        self.states = states
        self.children = differential.children_of(views, VOCABULARY)

    def ancestors(self, record: str) -> list[dict[str, Any]]:
        chain: list[dict[str, Any]] = []
        seen = {record}
        view = self.views.get(record)
        while view is not None and len(chain) < DEPTH:
            parent = _parent(view)
            if parent is None or parent in seen:
                break
            seen.add(parent)
            chain.append(node(parent, self.views, self.states))
            view = self.views.get(parent)
        return chain[::-1]

    def holding(self, record: str, children: bool = True) -> list[tuple[str, str]]:
        view = self.views.get(record)
        if view is None:
            return []
        found = [
            (edge.target, "blocks")
            for edge in view.dependencies
            if edge.type in VOCABULARY.blocking_types
            and differential.blocker_holds(self.views.get(edge.target), VOCABULARY)
        ]
        if children:
            found += [
                (child, "child")
                for child in differential.open_children(
                    record, self.views, self.children, VOCABULARY
                )
            ]
        return found

    def startable(self, record: str) -> bool:
        view = self.views.get(record)
        return view is not None and differential.is_ready(
            view, self.views, self.children, VOCABULARY
        )

    def waits(self, record: str) -> list[dict[str, Any]]:
        direct = self.holding(record)
        expanded = {record, *(target for target, _ in direct)}
        rows = []
        for target, via in direct:
            row = node(target, self.views, self.states)
            row.update(via=via, startable=self.startable(target), repeat=False)
            row["waits"] = self._waits(target, DEPTH - 1, expanded)
            rows.append(row)
        return rows

    def _waits(self, record: str, depth: int, expanded: set[str]) -> list[dict[str, Any]]:
        rows = []
        for target, via in self.holding(record):
            row = node(target, self.views, self.states)
            row.update(via=via, startable=self.startable(target), repeat=target in expanded)
            row["waits"] = []
            if not row["repeat"]:
                expanded.add(target)
                if depth > 1:
                    row["waits"] = self._waits(target, depth - 1, expanded)
            rows.append(row)
        return rows

    def parent_waits(self, record: str) -> dict[str, Any] | None:
        view = self.views.get(record)
        parent = _parent(view) if view is not None else None
        if parent is None:
            return None
        held = self.holding(parent, children=False)
        return {
            "id": parent,
            "waits": [node(target, self.views, self.states) for target, _ in held],
        }

    def _rank(self, record: str) -> tuple[int, str]:
        state = self.states.get(record)
        priority = str(state.fields.get("priority", "")) if state is not None else ""
        return (int(priority) if priority.isdigit() else LAST, record)

    def _planned(self, record: str, inside: set[str]) -> dict[str, Any]:
        held = [target for target, _ in self.holding(record, children=False)]
        row = node(record, self.views, self.states)
        row.update(
            startable=self.startable(record),
            inside=sorted(target for target in held if target in inside),
            outside=sorted(target for target in held if target not in inside),
        )
        return row

    def plan(self, record: str) -> dict[str, Any] | None:
        kids = [
            child
            for child in self.children.get(record, ())
            if child in self.views and not self.views[child].tombstoned
        ]
        if not kids:
            return None
        live = {child for child in kids if _open(self.views[child])}
        rows = {child: self._planned(child, live) for child in sorted(live, key=self._rank)}
        waves: list[list[dict[str, Any]]] = []
        placed: set[str] = set()
        while wave := [
            c for c, row in rows.items() if c not in placed and placed >= set(row["inside"])
        ]:
            waves.append([rows[child] for child in wave])
            placed.update(wave)
        return {
            "waves": waves,
            "circle": [row for child, row in sorted(rows.items()) if child not in placed],
            "done": [node(c, self.views, self.states) for c in sorted(kids) if c not in live],
        }

    def shown(self, record: str) -> dict[str, object]:
        return {
            "ancestors": self.ancestors(record),
            "waits": self.waits(record),
            "parent_waits": self.parent_waits(record),
            "map": self.plan(record),
        }
