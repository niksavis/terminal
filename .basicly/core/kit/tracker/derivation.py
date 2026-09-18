from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_HERE = Path(__file__).resolve().parent
_VIEWS_MODULE_NAME = "basicly_tracker_kit_views"


def _load_views() -> ModuleType:

    cached = sys.modules.get(_VIEWS_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_VIEWS_MODULE_NAME, _HERE / "views.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("the tracker kit's views.py is missing from beside derivation.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_VIEWS_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


views = _load_views()

GateRow = views.GateRow
Edge = views.Edge
RecordView = views.RecordView
GateVerdict = views.GateVerdict
Verdict = views.Verdict

DifferentialError = views.DifferentialError
QUERY_PHASE = views.QUERY_PHASE
QUERY_READY = views.QUERY_READY
QUERY_GATES = views.QUERY_GATES
QUERIES = views.QUERIES


@dataclass(frozen=True)
class Vocabulary:
    marker: str = "[harness-policy]"
    checkpoints: tuple[str, ...] = ("classify", "decompose", "ship")
    required_gates: tuple[str, ...] = ("verify",)
    engine_gate_providers: frozenset[str] = frozenset({"basicly-verify", "basicly-rubric"})
    worktree_ref_prefix: str = "worktree:"
    known_statuses: frozenset[str] = frozenset({
        "open",
        "in_progress",
        "blocked",
        "deferred",
        "draft",
        "closed",
        "tombstone",
        "pinned",
    })
    dispatchable_statuses: frozenset[str] = frozenset({
        "open",
        "in_progress",
        "blocked",
        "draft",
        "pinned",
    })
    closed_statuses: frozenset[str] = frozenset({"closed", "tombstone"})
    blocking_types: frozenset[str] = frozenset({"blocks"})
    parent_child_type: str = "parent-child"


DEFAULT_VOCABULARY = Vocabulary()


def marker_matches(text: str, marker: str) -> bool:

    stripped = text.strip()
    first_line = stripped.splitlines()[0] if stripped else ""
    return first_line == marker or first_line.startswith(marker + " ")


def checkpoint_marker(name: str, vocabulary: Vocabulary) -> str:
    return f"{vocabulary.marker} checkpoint={name} approved"


def approved_checkpoints(view: RecordView, vocabulary: Vocabulary) -> tuple[str, ...]:
    return tuple(
        name
        for name in vocabulary.checkpoints
        if any(marker_matches(text, checkpoint_marker(name, vocabulary)) for text in view.comments)
    )


def worktree_bound(view: RecordView, vocabulary: Vocabulary) -> bool:

    prefix = vocabulary.worktree_ref_prefix
    if not view.external_ref.startswith(prefix):
        return False
    name, sep, branch = view.external_ref[len(prefix) :].partition(":")
    return bool(sep and name and branch)


def gate_verdict(view: RecordView, vocabulary: Vocabulary) -> GateVerdict:

    required = vocabulary.required_gates
    rows = sorted(view.gates, key=lambda row: (row.gate, row.provider))
    engine = {row.gate: row for row in rows if row.provider in vocabulary.engine_gate_providers}
    latest = {row.gate: row for row in rows}
    failed = tuple(gate for gate in required if gate in engine and not engine[gate].passed)
    missing = tuple(gate for gate in required if gate not in engine)
    return GateVerdict(
        passed=tuple(gate for gate in required if gate in engine and engine[gate].passed),
        failed=failed,
        missing=missing,
        advisory=tuple(row for gate, row in latest.items() if gate not in required),
        disregarded=tuple(
            row
            for row in rows
            if row.gate in required and row.provider not in vocabulary.engine_gate_providers
        ),
        can_advance=not failed and not missing,
    )


def derive_phase(  # noqa: PLR0913 — one argument per derived input; see the docstring
    status: str,
    checkpoints: tuple[str, ...],
    bound: bool,
    gates: GateVerdict,
    has_children: bool,
    vocabulary: Vocabulary,
) -> str:

    if status in vocabulary.closed_statuses:
        return "done"
    verified = gates.can_advance and (bound or has_children)
    landed = gates.can_advance and (not bound or verified)
    ladder = (
        ("ship", "ship" in checkpoints and landed),
        ("verify", verified),
        ("build", bound),
        ("decompose", "decompose" in checkpoints or has_children),
        ("classify", "classify" in checkpoints),
    )
    for phase, reached in ladder:
        if reached:
            return phase
    return "intake"


def is_dispatchable(status: str, vocabulary: Vocabulary) -> bool:

    return status in vocabulary.dispatchable_statuses or status not in vocabulary.known_statuses


def children_of(views: Mapping[str, RecordView], vocabulary: Vocabulary) -> dict[str, list[str]]:

    children: dict[str, list[str]] = {}
    for record in sorted(views):
        for edge in views[record].dependencies:
            if edge.type == vocabulary.parent_child_type:
                children.setdefault(edge.target, []).append(record)
    return children


def is_ready(
    view: RecordView,
    views: Mapping[str, RecordView],
    children: Mapping[str, Sequence[str]],
    vocabulary: Vocabulary,
) -> bool:

    if view.tombstoned:
        return False
    if not is_dispatchable(view.status, vocabulary):
        return False
    if children.get(view.record):
        return False
    for edge in view.dependencies:
        if edge.type not in vocabulary.blocking_types:
            continue
        blocker = views.get(edge.target)
        if blocker is None or blocker.status not in vocabulary.closed_statuses:
            return False
    return True


def verdicts(
    views: Mapping[str, RecordView], vocabulary: Vocabulary = DEFAULT_VOCABULARY
) -> dict[str, Verdict]:

    children = children_of(views, vocabulary)
    answers: dict[str, Verdict] = {}
    for record in sorted(views):
        view = views[record]
        gates = gate_verdict(view, vocabulary)
        answers[record] = Verdict(
            phase=derive_phase(
                view.status,
                approved_checkpoints(view, vocabulary),
                worktree_bound(view, vocabulary),
                gates,
                bool(children.get(record)),
                vocabulary,
            ),
            ready=is_ready(view, views, children, vocabulary),
            gates=gates,
        )
    return answers
