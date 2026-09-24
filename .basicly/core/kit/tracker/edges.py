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
        raise ImportError(f"the tracker kit's {file_name} is missing from beside edges.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


queries = _load("queries.py", "basicly_tracker_kit_queries")
differential = queries.differential


class RefusedEdgeError(differential.events.LedgerError):
    pass


def refuse_edge(ledger: Path, record: str, target: str, edge_type: str) -> None:

    vocabulary = differential.DEFAULT_VOCABULARY
    if edge_type not in vocabulary.edge_types:
        known = ", ".join(sorted(vocabulary.edge_types))
        raise RefusedEdgeError(f"{edge_type!r} is not an edge type; use one of {known}")
    views, _ = queries.views_and_children(ledger)
    if any(edge.target == target and edge.type == edge_type for edge in views[record].dependencies):
        raise RefusedEdgeError(f"{record} already has a {edge_type} edge on {target}")
    if (
        edge_type in vocabulary.blocking_types
        and views[target].status in vocabulary.closed_statuses
    ):
        raise RefusedEdgeError(
            f"{target} is closed, so a {edge_type} edge on it holds nothing back; "
            f"name an open record, or use related to keep the link"
        )


def refuse_cycle(ledger: Path, record: str, target: str, edge_type: str) -> None:

    views, _ = queries.views_and_children(ledger)
    seen = set()
    frontier = [target]
    while frontier:
        current = frontier.pop()
        if current == record:
            raise RefusedEdgeError(
                "an edge "
                + record
                + " -> "
                + target
                + " of type "
                + edge_type
                + " closes a cycle, which leaves every record on it permanently unready"
            )
        if current in seen:
            continue
        seen.add(current)
        view = views.get(current)
        if view is None:
            continue
        frontier.extend(edge.target for edge in view.dependencies if edge.type == edge_type)


def refuse_retraction(views: Any, record: str, target: str, edge_type: str) -> None:

    parent_child = differential.DEFAULT_VOCABULARY.parent_child_type
    if edge_type == parent_child:
        raise RefusedEdgeError(
            f"a {parent_child!r} edge is not retractable: removing it re-parents {record} "
            f"while its id still spells its parent, so re-parenting needs its own verb"
        )
    held = views.get(record)
    if held is None or not any(
        edge.target == target and edge.type == edge_type for edge in held.dependencies
    ):
        raise RefusedEdgeError(
            f"{record} holds no {edge_type!r} edge to {target}, so there is nothing to retract; "
            f"the edge is recorded on the dependent, so check both ids with show {record}"
        )
