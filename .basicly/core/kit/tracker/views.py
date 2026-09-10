"""What each side reports about one record, and what a derivation concludes about it.

Five frozen records and no behaviour. The boundary is *the shape both sides agree to speak
in*, against :mod:`derivation`, which reads that shape and concludes, and
:mod:`differential`, which fills it from a store. A differential is only meaningful while the
owned side and a foreign reference report the same fields, so the fields are declared once
here rather than twice.

Split out of `derivation` when that module crossed the 4,000-token cap on the way out of
`differential.py`'s 11,110 (basicly-oii83r's blocker). Imports nothing at all, from the kit or
otherwise beyond the standard library, which is what makes it the bottom of this stack.
"""

# comment-density-waiver: cohesion: 73.4% because the module is five frozen records and no
# behaviour - the docstrings ARE the payload. Each field's contract is what makes a differential
# meaningful: two sides may only be compared while they report the same fields, so what a
# field admits is declared once here instead of twice. Deleting that leaves five anonymous
# tuples. Merging back into `derivation` is not available: 3597 + 1236 crosses the 4000 cap.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- what each side reports about one record ----------------------------------


class DifferentialError(Exception):
    """A differential this kit cannot carry out.

    The kit's own error, raised by the derivation and re-exported by `differential` under the
    same name, so one object serves every `except` in the tree.
    """


# §5's list, and deliberately closed: these are the queries the loop advances on, so a
# fourth is a decision rather than an addition.
QUERY_PHASE = "phase"
QUERY_READY = "ready"
QUERY_GATES = "gates"
QUERIES = (QUERY_PHASE, QUERY_READY, QUERY_GATES)


@dataclass(frozen=True)
class GateRow:
    """One recorded gate result, as a live gate query reports it."""

    gate: str
    provider: str
    passed: bool


@dataclass(frozen=True)
class Edge:
    """One outgoing dependency edge: this record depends on *target*, of type *type*.

    Held on the **dependent**, which is where both stores put it — `migrate.py` records an
    edge event on the dependent record, and a live tracker lists it under that record's
    ``dependencies``. Dependents are therefore never supplied: they are inverted from the
    population by :func:`children_of`, so the two sides cannot disagree merely because one
    of them was asked for a field the other does not carry (the export has no
    ``dependents`` key; a live record query does).
    """

    target: str
    type: str


@dataclass(frozen=True)
class RecordView:
    """One record as one tracker reports it — exactly the inputs the queries read.

    Deliberately narrow. Everything a store holds that no query reads — titles,
    descriptions, timestamps, a store's ``source_repo_path`` — is left out, so an incidental
    difference between the two stores cannot be reported as a disagreement about a verdict.
    The export's comment text may be redacted on publish while the live tracker's is not,
    which is exactly such a difference: it changes the bytes and it cannot change a marker.

    Attributes:
        record: The record's id.
        status: Its status.
        external_ref: The worktree binding, or empty.
        comments: Comment texts in order — the carrier for checkpoint markers.
        dependencies: Outgoing dependency edges.
        gates: Recorded gate results. Empty from any snapshot-backed source; see
            :data:`EXPORT_CANNOT_EXPRESS`.
        tombstoned: The store says this record is deleted.
    """

    record: str
    status: str = ""
    external_ref: str = ""
    comments: tuple[str, ...] = ()
    dependencies: tuple[Edge, ...] = ()
    gates: tuple[GateRow, ...] = ()
    tombstoned: bool = False


# --- the verdicts -------------------------------------------------------------


@dataclass(frozen=True)
class GateVerdict:
    """The advance decision derived from one record's gate rows.

    Mirrors `basicly.policy.GateStatus`, including the part that is easy to get wrong: a
    **required** gate counts only a result from :attr:`Vocabulary.engine_gate_providers`, and
    a foreign result on a required gate is reported as *disregarded* rather than dropped, so
    a gate reading missing while the tracker plainly shows a pass is explicable
    (basicly-jr0l.51).

    Attributes:
        passed: Required gates with a passing engine result.
        failed: Required gates with a failing engine result.
        missing: Required gates with no engine result.
        advisory: Gates recorded that are not required, any provider.
        disregarded: Results on a required gate from a provider that does not count.
        can_advance: No required gate failed and none is missing.
    """

    passed: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    advisory: tuple[GateRow, ...] = ()
    disregarded: tuple[GateRow, ...] = ()
    can_advance: bool = False


@dataclass(frozen=True)
class Verdict:
    """One store's answers to the three queries, about one record."""

    phase: str
    ready: bool
    gates: GateVerdict

    def answer(self, query: str) -> Any:
        """This verdict's answer to *query*.

        Raises:
            DifferentialError: *query* is not one of :data:`QUERIES`. Refused rather than
                returning ``None``, which would compare equal on both sides and report a
                query nobody answered as agreement.
        """
        if query == QUERY_PHASE:
            return self.phase
        if query == QUERY_READY:
            return self.ready
        if query == QUERY_GATES:
            return self.gates
        raise DifferentialError(f"unknown query {query!r}; expected one of {', '.join(QUERIES)}")
