"""The tracker's phase, ready and gate derivation, run identically over either side.

**The one rule, and this module is it: nothing here reads a store.** Every function takes a
:class:`views.RecordView` and a :class:`Vocabulary` and returns a value, so the same code
answers the same question about the owned ledger and about a foreign reference - which is the
whole claim a differential makes. A derivation that could reach a file would let the two sides
run different code and still agree, and an agreement like that proves nothing.

The boundary is that purity, against :mod:`differential`, which folds the owned side, audits a
reference and compares the two; and against :mod:`views`, which declares the shape both sides
report in. Split out when `differential.py` reached 11,110 tokens with no headroom, so the fix
to its fold could not be written (the blocker on basicly-oii83r).
"""

# comment-density-waiver: cohesion: 52.7% after this module was split out of a 11,110-token
# `differential.py`. Splitting raises the prose share of both halves by construction - the code
# divides and each half still owes a contract docstring - and it is the second time in one pass
# that the size ratchet and this one pulled opposite ways on the same edit. Every docstring
# here states why a derivation may not read a store, or which measurement a threshold came
# from; none narrates its body.

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
    """Load ``views.py`` from beside this file, the kit's by-path way.

    Cached on the published name because two loads give two ``RecordView`` classes and an
    ``isinstance`` against the wrong one is false for the right reason.
    """
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

# Re-exported under the names every consumer already reads, for `differential`'s reason: one
# object per name, so `isinstance` and `except` behave exactly as before the split.
GateRow = views.GateRow
Edge = views.Edge
RecordView = views.RecordView
GateVerdict = views.GateVerdict
Verdict = views.Verdict

# The error and the closed query set are declared in `views`, beside `Verdict.answer` which
# reads them; re-exported here under the names every consumer already uses.
DifferentialError = views.DifferentialError
QUERY_PHASE = views.QUERY_PHASE
QUERY_READY = views.QUERY_READY
QUERY_GATES = views.QUERY_GATES
QUERIES = views.QUERIES


# --- errors -------------------------------------------------------------------


# --- the three queries --------------------------------------------------------


# --- the derivation's vocabulary ----------------------------------------------


@dataclass(frozen=True)
class Vocabulary:
    """The engine's names for the things the three queries read.

    Every default mirrors a constant in the engine and names it, so a consumer gets a
    working derivation and this repo can pass its own configuration instead. Nothing here is
    read from a config file — the kit takes it as an argument (§4).

    Attributes:
        marker: The comment-marker prefix (`basicly.policy.MARKER`).
        checkpoints: The human checkpoint names (`basicly.config.CHECKPOINTS`).
        required_gates: Gates that must pass to advance
            (`basicly.config.DEFAULT_REQUIRED_GATES`).
        engine_gate_providers: Providers whose result counts on a *required* gate
            (`basicly.config.ENGINE_GATE_PROVIDERS`). A foreign result on a required gate is
            disregarded, because a gate report authenticates nothing.
        worktree_ref_prefix: How an in-flight worktree binding is spelled on
            ``external_ref`` (`basicly.loop_state.WORKTREE_REF_PREFIX`).
        known_statuses: The tracker's own status vocabulary
            (`basicly.loop_state.KNOWN_STATUSES`).
        dispatchable_statuses: Statuses under which work may be dispatched
            (`basicly.loop_state.DISPATCHABLE_STATUSES`).
        closed_statuses: Statuses that satisfy a blocking edge — terminal ones.
        blocking_types: Edge types that hold a record back until the target is closed
            (`basicly.merge.blocking_dependencies` reads exactly ``blocks``).
        parent_child_type: The edge type that makes a record somebody's child, and so makes
            its target a decomposed parent (`basicly.loop_state._has_children`).
    """

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


# --- the derivation, run identically over both sides --------------------------


def marker_matches(text: str, marker: str) -> bool:
    """Token-exact marker match on a comment's first line.

    Mirrors `basicly.policy._marker_matches`. A bare prefix match would cross-count names
    that extend each other (``verify`` against ``verify-full``), so the marker must be the
    whole first line or be followed by a space.
    """
    stripped = text.strip()
    first_line = stripped.splitlines()[0] if stripped else ""
    return first_line == marker or first_line.startswith(marker + " ")


def checkpoint_marker(name: str, vocabulary: Vocabulary) -> str:
    """The comment a human approval of the *name* checkpoint is recorded as."""
    return f"{vocabulary.marker} checkpoint={name} approved"


def approved_checkpoints(view: RecordView, vocabulary: Vocabulary) -> tuple[str, ...]:
    """The checkpoints approved on *view*, in :attr:`Vocabulary.checkpoints` order."""
    return tuple(
        name
        for name in vocabulary.checkpoints
        if any(marker_matches(text, checkpoint_marker(name, vocabulary)) for text in view.comments)
    )


def worktree_bound(view: RecordView, vocabulary: Vocabulary) -> bool:
    """Whether *view* carries an in-flight worktree binding.

    Mirrors `basicly.loop_state.parse_worktree_ref`'s truthiness: the prefix alone is not a
    binding, both halves have to be there, and a foreign ``external_ref`` reads as unbound.
    """
    prefix = vocabulary.worktree_ref_prefix
    if not view.external_ref.startswith(prefix):
        return False
    name, sep, branch = view.external_ref[len(prefix) :].partition(":")
    return bool(sep and name and branch)


def gate_verdict(view: RecordView, vocabulary: Vocabulary) -> GateVerdict:
    """Classify *view*'s gate rows against the required set.

    A live tracker keeps one result per ``(gate, provider)`` rather than one per gate, so
    the engine's own result is selected independently instead of by collapsing every row for
    a gate and taking the last — a foreign row landing last would otherwise become authoritative
    (basicly-jr0l.51).

    The row tuples are **sorted**, and that is not cosmetic: a gate query guarantees no row
    order and the ledger's order is the write order, so an unsorted verdict would compare
    unequal between two stores holding the same rows and report a disagreement that is only
    an ordering.
    """
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
    """The furthest loop phase the record's own state evidences.

    Mirrors `basicly.loop_state.derive_phase`, ladder and all, including the part that rule
    exists for: the ship rung requires the node to have **landed**, not merely to carry an
    approved ship checkpoint, because a ship approval recorded out of order on a node that
    never built otherwise derived ``ship`` and closed a record with no work done
    (basicly-k35r, basicly-jr0l.49). Takes the derived inputs rather than a
    :class:`RecordView` so it is the same shape as the engine's function and can be diffed
    against it by eye.
    """
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
    """Whether work may be dispatched on a record in *status*.

    Mirrors `basicly.loop_state.is_dispatchable`: a status outside the known vocabulary is
    **admitted**, because a project may define its own and refusing an unknown one would
    both defund real work and let its parent fan in over it.
    """
    return status in vocabulary.dispatchable_statuses or status not in vocabulary.known_statuses


def children_of(views: Mapping[str, RecordView], vocabulary: Vocabulary) -> dict[str, list[str]]:
    """Parent id to child ids, inverted from the population's outgoing edges.

    Both stores record the parent-child edge on the child, so the parent's side of it is
    derived here rather than asked for — see :class:`Edge`.
    """
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
    """Whether *view* is in the ready set: actionable now, on its own.

    Three clauses, each mirroring one the engine already applies in
    `basicly.supervise.ready_lanes` and `basicly.merge.blocking_dependencies`:

    1. the status admits dispatch (`loop_state.is_dispatchable`);
    2. every blocking dependency is closed — an edge into a record the population does not
       hold is **not** treated as satisfied, because an unknown blocker is unknown rather
       than absent;
    3. it has no parent-child children — a decomposed parent is not itself the work.

    What is deliberately not here is the rest of `ready_lanes`' filter: a pending decision,
    a live lane, and the ``phase == "build"`` rung are engine session state, not facts either
    store holds, so including them would make the ready set depend on something the
    comparison cannot read from either side.

    A tombstoned record is refused before any of it. The live tracker expresses a deletion by
    not returning the record at all, so it has no ready set to disagree with; the owned ledger
    expresses it as an event and keeps the record in the fold (`events.py`'s ``tombstoned``),
    which leaves the *status* untouched — ``_apply_tombstone`` writes the flag and nothing
    else. Without this clause a deleted record whose last status was ``open`` reads as
    dispatchable, so after the flip (basicly-vkh0.19) the scheduler would hand out work on a
    record somebody deleted.
    """
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
    """Every record's answers to the three queries, derived from *views* alone.

    The single derivation both sides go through. Called once per store, so a disagreement is
    about a fact one of them holds and the other does not — never about two copies of a
    rule.
    """
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
