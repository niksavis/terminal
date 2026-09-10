r"""The shadow differential: the owned ledger held against the **live** tracker.

Step 2 of the four-step cutover (§5 in `SPEC.md`, basicly-vkh0.18). The
owned event log answers the three queries the harness actually runs on — phase derivation,
the ready set, and gate status — and this module compares those answers, record by record
across the ledger's whole population, against the same answers read from the tracker that is
still authoritative. Step 1 is `migrate.py`; the dual write and the flip (basicly-vkh0.19)
are what a clean report licenses.

## The one constraint the whole module is shaped by

§5.1: the differential must compare against the **live tracker**, never against a re-import
of its own export — *two derivatives of one lossy snapshot agree with each other and prove
nothing*. That is not advice about how to hold the tool; it is a property the harness has to
**refuse to run without**, because the failure mode is a clean report. So the reference side
is not a mapping this module accepts on trust: it is a :class:`ReferenceSource` that is
audited first, and every audit finding is a refusal that makes the report unclean.

Three findings, each catching a different route to a self-agreeing comparison:

``reimported-own-export``
    The reference read the very snapshot the ledger was imported from. `migrate.py` records
    the export's sha256 as ``import_digest`` on every ``created`` event so *"a later reader
    can say which snapshot a record arrived from"*; this is that reader. The digest is
    recomputed here from the bytes the reference declares it read, so the check is a
    verification rather than a caller's assertion about itself.
``export-backed-reference``
    The reference read *an* export — any export. Still refused, and on measured grounds
    rather than on principle: a gate-report row is visible to a live gate query and is
    **absent from the JSONL export** (probed 2026-08-06 on a throwaway tracker: the
    exported record carried no gate field at all, while a checkpoint comment marker written
    beside it survived). An export therefore cannot answer one of the three queries, so a
    snapshot-backed reference is silent exactly where the live tracker is the only witness.
``derived-from-owned-ledger``
    The reference is some *other* function of the owned event log — a re-fold, a re-export
    and re-import, a view builder pointed at the same directory — and so declares no
    snapshot at all. Caught by **perturbation**, which is the only route that does not rely
    on the reference describing itself: :func:`probe_events` appends one synthetic status
    event to the event set the reference is handed, and a source whose answers move with it
    is a derivative. A live source ignores that argument but not its own store, which
    anything writing the tracker mid-run moves under it — so movement is charged to the
    probe only when a re-read *without* it reproduces the baseline (basicly-vkh0.35, where
    the missing control refused the live tracker itself).

Where that stops, stated so the report is not read as more than it is: a reference that
reads a snapshot **from disk** while declaring none, or that memoises its answers, defeats
both the digest check and the perturbation probe. The audit raises the cost of a
self-agreeing comparison; it cannot make one impossible. What closes the remaining gap is
:attr:`DifferentialReport.conclusive` — see below.

## A clean report is not enough; it also has to be conclusive

The hazard this design keeps paying for is a gate that passes because it never fired. A
comparison over a population where every record gives the **same** answer to a query has
discriminated nothing, and gate status is the live case rather than a hypothetical one: on
the tracker this was built against every record reported zero gate rows, so that query is
constant and a differential that only reported ``clean`` would be reporting the absence of
evidence as agreement. :attr:`DifferentialReport.inconclusive` names every query whose
answers were constant across both sides, and :attr:`clean` and :attr:`conclusive` are
separate properties so a caller cannot get the second by asking for the first.

## One derivation, two stores

What the flip replaces is the **store**, not the query layer: after basicly-vkh0.19 the
engine still derives a phase, it just reads a different tracker. So both sides supply a
:class:`RecordView` — the inputs the three queries read — and this module derives the
verdicts **once**, with one implementation, for both. A disagreement is then a disagreement
about a *fact*, which is what shadow mode is checking, rather than a difference between two
copies of the derivation. Two copies of a rule that disagree is the defect class this design
is built to avoid (see `events.py`'s single accumulator).

The derivation's vocabulary — the checkpoint names, the required gates, which providers
count, how a worktree binding is spelled — is the engine's and is taken as an argument
(:class:`Vocabulary`). The defaults mirror `basicly.config` and `basicly.loop_state` so the
kit works in a repository that has never heard of this harness, and each one names the
engine constant it mirrors so drift is visible rather than silent.

## What this module may not do

Kit rules (§4): **no basicly**, standard library only, no network, no subprocess. It reads
the ledger and takes the reference side as an injected callable — which is also the only
shape available, because reading a live tracker means spawning a process and the kit may not.
The engine's side of that seam is `basicly.loop_state` and `basicly.policy`: one bulk
record query answers status, ``external_ref``, dependencies and comments for the whole
population in a single spawn (measured: 639 records in 0.91s), and a gate query answers
what the export cannot.

It must stay parseable by an interpreter older than this repo's 3.14 floor: no syntax newer
than 3.9, and one exception class per handler (`.basicly/core/kit/README.md`).
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

# --- the sibling importer, and the event log under it -------------------------

_HERE = Path(__file__).resolve().parent
_MIGRATE_MODULE_NAME = "basicly_tracker_kit_migrate"


def _load_migrate() -> ModuleType:
    """Load ``migrate.py`` from beside this file, without touching ``sys.path``.

    The same by-path load `events.py` uses for `ids.py` and `migrate.py` uses for
    `events.py`, and for the same reason: the kit is a set of sibling files rather than a
    package, and a library loaded into somebody else's process may not claim a bare name.

    The importer rather than the event log directly, and not for convenience: it owns the
    ``edge`` vocabulary this module reads and the ``import_digest`` pin the audit checks. A
    second spelling of either here is the drift `events.py` documents as the defect this
    design keeps paying for, and loading through `migrate` also guarantees one ``Event``
    class in the process — two loads of one file give two, and an ``isinstance`` against the
    wrong one is false for the right reason.
    """
    cached = sys.modules.get(_MIGRATE_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_MIGRATE_MODULE_NAME, _HERE / "migrate.py")
    if spec is None or spec.loader is None:
        raise DifferentialError(
            "the tracker kit's migrate.py is missing from beside differential.py"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MIGRATE_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


migrate = _load_migrate()
events = migrate.events

_DERIVATION_MODULE_NAME = "basicly_tracker_kit_derivation"


def _load_derivation() -> ModuleType:
    """Load ``derivation.py`` from beside this file, :func:`_load_migrate`'s way.

    A separate loader rather than a reach through ``migrate``: the derivation imports nothing
    from the kit, so routing it through the importer would invent a dependency the module does
    not have. Cached on the published name for the same reason as every sibling here - two
    loads of one file give two ``RecordView`` classes, and an ``isinstance`` against the wrong
    one is false for the right reason.
    """
    cached = sys.modules.get(_DERIVATION_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_DERIVATION_MODULE_NAME, _HERE / "derivation.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("the tracker kit's derivation.py is missing from beside differential.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_DERIVATION_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


derivation = _load_derivation()

_PROVENANCE_MODULE_NAME = "basicly_tracker_kit_provenance"


def _load_provenance() -> ModuleType:
    """Load ``provenance.py`` from beside this file, :func:`_load_migrate`'s way.

    For its **edge dialect** alone. The log holds two spellings of an edge's structural
    fields and `provenance` is where that pair is declared, so reading it from there is what
    stops the two folds disagreeing about one input - which is the defect basicly-oii83r
    records, and the mirror of the one `basicly-svct4w` fixed from the other side.
    """
    cached = sys.modules.get(_PROVENANCE_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_PROVENANCE_MODULE_NAME, _HERE / "provenance.py")
    if spec is None or spec.loader is None:
        raise DifferentialError("the tracker kit's provenance.py is missing from beside this file")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PROVENANCE_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


provenance = _load_provenance()

# Dialect to the pair of structural keys that spells it, taken from `provenance` rather than
# respelled: a second copy of this table is exactly how the two folds came to read different
# populations of one log (basicly-oii83r).
_EDGE_KEYS = provenance.labels.DIALECT_KEYS


# The derivation's surface, re-exported under the names every consumer already reads. Aliases
# rather than a `from` import because the kit is not a package: one object per name, so an
# `except DifferentialError` and an `isinstance(x, RecordView)` behave exactly as before.
DifferentialError = derivation.DifferentialError
Vocabulary = derivation.Vocabulary
DEFAULT_VOCABULARY = derivation.DEFAULT_VOCABULARY
GateRow = derivation.GateRow
Edge = derivation.Edge
RecordView = derivation.RecordView
GateVerdict = derivation.GateVerdict
Verdict = derivation.Verdict
QUERY_PHASE = derivation.QUERY_PHASE
QUERY_READY = derivation.QUERY_READY
QUERY_GATES = derivation.QUERY_GATES
QUERIES = derivation.QUERIES
marker_matches = derivation.marker_matches
checkpoint_marker = derivation.checkpoint_marker
approved_checkpoints = derivation.approved_checkpoints
worktree_bound = derivation.worktree_bound
gate_verdict = derivation.gate_verdict
derive_phase = derivation.derive_phase
is_dispatchable = derivation.is_dispatchable
children_of = derivation.children_of
is_ready = derivation.is_ready
verdicts = derivation.verdicts


# The event kind that carries a gate result on the owned ledger, and its payload's names.
#
# The kind is `events.py`'s (basicly-vkh0.36); the payload names are spelled here because this
# module is the kind's first **reader** and the differential cannot answer §5's third query
# without them. The export has no gate field at all (see :data:`EXPORT_CANNOT_EXPRESS`), so
# `migrate.py` has nothing to import and the writer is the dual write (basicly-vkh0.19) —
# which is the whole reason the third query is the one the import step could never have
# covered.
KIND_GATE = events.KIND_GATE
GATE_NAME_KEY = "gate"
GATE_PROVIDER_KEY = "provider"
GATE_PASSED_KEY = "passed"

# --- what the audit refuses ---------------------------------------------------

RULE_REIMPORTED_EXPORT = "reimported-own-export"
RULE_EXPORT_BACKED = "export-backed-reference"
RULE_DERIVED_FROM_LEDGER = "derived-from-owned-ledger"

# §5.1's sentence, quoted rather than paraphrased: it is the reason every one of these
# refusals exists and it is what a reader of the report needs to see.
LOSSY_SNAPSHOT_REASON = (
    "two derivatives of one lossy snapshot agree with each other and prove nothing"
)

# The measured asymmetry behind RULE_EXPORT_BACKED. Recorded here rather than in prose only,
# because it is the fact that makes the refusal evidence instead of caution.
EXPORT_CANNOT_EXPRESS = (
    "a gate-report row is visible to a live gate query and absent from the JSONL export, so an "
    "export-backed reference cannot answer the gate-status query at all"
)


# --- the owned side: views folded out of the event log ------------------------


def views_from_events(ledger_events: Iterable[Any]) -> dict[str, RecordView]:
    """The owned tracker's :class:`RecordView` for every record in *ledger_events*.

    The fold is the authority for status, fields and comments. Edges and gate rows are read
    from their own events directly because `events.py` has a handler for neither kind — it
    counts them in :attr:`FoldResult.delegated_kinds` and folds no state, which is
    tolerant direction working as specified rather than a gap to route around.

    A gate row keyed ``(gate, provider)`` keeps only its latest event, because that is what
    a live tracker holds: one result per pair rather than one per gate. Collapsing to one
    row per gate here would make a foreign provider's result outvote the engine's, which is
    the defect
    :func:`gate_verdict` exists to avoid (basicly-jr0l.51).

    An edge is held **last statement wins** per identity, which is what makes
    `events.KIND_EDGE_RETRACTED` a retraction and not a deletion: the withdrawn edge is
    absent here while both events stay in the log, and an edge withdrawn and re-asserted
    the other way round reads as present in the new direction with no cycle through the
    old one. `_apply_tombstone`'s shape for a record, one level down.

    That identity key is also what makes a **count** off this fold a count of relations: nine
    parent-child relations in this ledger are stated by two edge events each - an import that
    carried `asserted_at` and one that did not - and holding them per event put five extra
    children on one epic's `tracker show` (basicly-vkh0.52).

    It folds here and not in `provenance.py` because the two write the edge payload in
    different dialects (`fsck.EDGE_KINDS`); this reads the engine writer's.
    """
    collected = list(ledger_events)
    folded = events.fold(collected)
    edges: dict[str, dict[Edge, bool]] = {}
    gates: dict[str, dict[tuple[str, str], GateRow]] = {}
    for event in events.canonical_order(collected):
        if event.kind in (migrate.KIND_EDGE, events.KIND_EDGE_RETRACTED):
            target, edge_type = _edge_fields(event.payload)
            if isinstance(target, str) and isinstance(edge_type, str):
                held = edges.setdefault(event.record, {})
                held[Edge(target=target, type=edge_type)] = event.kind == migrate.KIND_EDGE
        elif event.kind == KIND_GATE:
            gate = event.payload.get(GATE_NAME_KEY)
            provider = event.payload.get(GATE_PROVIDER_KEY)
            if isinstance(gate, str) and isinstance(provider, str):
                row = GateRow(gate, provider, bool(event.payload.get(GATE_PASSED_KEY)))
                gates.setdefault(event.record, {})[(gate, provider)] = row
    views: dict[str, RecordView] = {}
    for record, state in folded.records.items():
        external_ref = state.fields.get("external_ref")
        views[record] = RecordView(
            record=record,
            status=state.status or "",
            external_ref=external_ref if isinstance(external_ref, str) else "",
            comments=tuple(state.comments),
            dependencies=tuple(edge for edge, held in edges.get(record, {}).items() if held),
            gates=tuple(gates.get(record, {}).values()),
            tombstoned=state.tombstoned,
        )
    return views


def _edge_fields(payload: Any) -> tuple[object, object]:
    """One edge payload's target and type, in whichever of the two spellings it carries.

    Reading only `migrate.py`'s pair made this fold blind to the declared one: measured on a
    four-edge fixture in the declared spelling it read **zero**, against four for the same
    fixture in the engine's (basicly-oii83r). The record predicted one; zero is what a reader
    matching neither key returns, and it is the same total blindness `provenance.fold_edges`
    had from the other side before `basicly-svct4w`.
    """
    keys = _EDGE_KEYS[provenance.edge_dialect(payload)]
    return payload.get(keys[0]), payload.get(keys[1])


def edge_dialects(ledger_events: Iterable[Any]) -> tuple[str, ...]:
    """Which edge spellings *ledger_events* actually holds, sorted, with none as empty.

    The fold reports the dialect rather than only counting, for `provenance.EdgeFold`'s
    reason: an empty edge set is otherwise the same answer for a log with no edges and a log
    whose every edge the reader could not parse, and those are opposite facts.
    """
    seen = {
        provenance.edge_dialect(event.payload)
        for event in ledger_events
        if getattr(event, "kind", "") in (migrate.KIND_EDGE, events.KIND_EDGE_RETRACTED)
    }
    return tuple(sorted(seen))


def read_ledger(directory: Path | str) -> list[Any]:
    """Every event in the ledger at *directory*, quarantined lines dropped.

    Quarantine is `fsck`'s business (basicly-vkh0.15) and not silently swallowed here: a
    line the fold cannot parse is a line neither store's verdict can rest on, and a
    differential that refused to run because of one would be unable to report the
    disagreement it exists for.
    """
    found, _ = events.read_events(directory)
    return found


# --- auditing the reference side ----------------------------------------------


@dataclass(frozen=True)
class ReferenceSource:
    """Where the reference verdicts come from, in a form the audit can check.

    Attributes:
        views: The reference's record views. Called with the owned event set **solely** so
            :func:`probe_events` can perturb it: a live source ignores the argument
            entirely, and one that does not is a derivative of the ledger it is supposed to
            be checked against. It is called more than once per run.
        snapshot: The export text this source read, when it read one. ``None`` for a live
            source. The digest is computed here from these bytes rather than taken as a
            claim, so :data:`RULE_REIMPORTED_EXPORT` rests on content.
    """

    views: Callable[[Sequence[Any]], Mapping[str, RecordView]]
    snapshot: str | None = None


@dataclass(frozen=True)
class Refusal:
    """One reason the reference side is not the live tracker."""

    rule: str
    detail: str


@dataclass(frozen=True)
class Inconclusive:
    """One thing the run could not establish, as opposed to one it disproved.

    Attributes:
        subject: What proved nothing — a query name from :data:`QUERIES` whose answers were
            constant, or an audit rule the ledger was too empty to check. Not typed as a
            query: an audit that could not run is exactly as disqualifying as a query that
            could not discriminate, and splitting them would let a caller check one list.
        reason: Why, in the terms a reader can act on.
    """

    subject: str
    reason: str


def imported_digests(ledger_events: Iterable[Any]) -> frozenset[str]:
    """The export digests the ledger's records were imported from.

    `migrate.py` records the export's sha256 under ``import_digest`` on each ``created``
    event, and on that event only, so that a per-snapshot value cannot destabilise an event
    id. This is the reader that pin was put there for.
    """
    found: set[str] = set()
    for event in ledger_events:
        if event.kind != events.KIND_CREATED:
            continue
        digest = event.payload.get(migrate.DIGEST_KEY)
        if isinstance(digest, str) and digest:
            found.add(digest)
    return frozenset(found)


def probe_events(ledger_events: Sequence[Any], vocabulary: Vocabulary) -> list[Any]:
    """*ledger_events* plus one synthetic status event, for the independence probe.

    The perturbation has to be visible in a :class:`RecordView`, so it is a status the
    record does not already hold: the target is the lexicographically first record, and the
    new status is ``closed`` unless it is already closed, in which case ``open``. Both
    change the folded status, and both change every query's answer for that record, so a
    derivative moves however it derives.

    The event is constructed rather than appended: nothing is written, the ledger is not
    touched, and the probe costs no clock. Its sequence number is one past the record's
    highest so the fold takes it as the record's latest, and its id is content-derived like
    any other so two probes of one ledger produce the same event.

    Returns the events unchanged when there is nothing to perturb — an empty ledger has no
    record whose answers could move, which :func:`audit_reference` reports as inconclusive
    rather than as a pass.
    """
    folded = events.fold(ledger_events)
    if not folded.records:
        return list(ledger_events)
    record = sorted(folded.records)[0]
    state = folded.records[record]
    status = "open" if state.status in vocabulary.closed_statuses else "closed"
    payload = {"status": status, migrate.PROVENANCE_KEY: "differential-probe"}
    totals = events.accumulate(state.totals, events.KIND_STATUS, payload)
    probe = events.Event(
        id=events.event_id_for(record, events.KIND_STATUS, payload),
        record=record,
        seq=state.max_seq + 1,
        kind=events.KIND_STATUS,
        actor="differential-probe",
        ts="",
        payload=payload,
        totals=totals,
    )
    return [*ledger_events, probe]


def audit_reference(
    source: ReferenceSource,
    ledger_events: Sequence[Any],
    baseline: Mapping[str, RecordView],
    vocabulary: Vocabulary = DEFAULT_VOCABULARY,
) -> tuple[list[Refusal], list[Inconclusive]]:
    """Every reason *source* is not the live tracker, plus what could not be established.

    Runs the three checks the module docstring names, in the order that puts the sharpest
    diagnosis first: a digest match says *this is the snapshot you were built from*, a
    declared snapshot says *this is an export*, and the perturbation probe is what catches a
    derivative that declares nothing.

    *baseline* is the reference's answers about the unperturbed ledger, passed in rather than
    fetched here: an unmoved reference then costs **one** extra call, and only one that moved
    pays for the control read. Reading the live tracker is a process spawn on the engine's side
    of the seam, and a probe that tripled its cost every run would argue for switching it off.
    """
    refusals: list[Refusal] = []
    unproven: list[Inconclusive] = []
    if source.snapshot is not None:
        digest = hashlib.sha256(source.snapshot.encode("utf-8")).hexdigest()
        if digest in imported_digests(ledger_events):
            refusals.append(
                Refusal(
                    RULE_REIMPORTED_EXPORT,
                    f"the reference read the export this ledger was imported from "
                    f"(sha256 {digest}): {LOSSY_SNAPSHOT_REASON}",
                )
            )
        else:
            refusals.append(
                Refusal(
                    RULE_EXPORT_BACKED,
                    f"the reference read an export rather than the live tracker "
                    f"(sha256 {digest}): {EXPORT_CANNOT_EXPRESS}, and {LOSSY_SNAPSHOT_REASON}",
                )
            )
    perturbed = probe_events(ledger_events, vocabulary)
    if len(perturbed) == len(ledger_events):
        unproven.append(
            Inconclusive(
                RULE_DERIVED_FROM_LEDGER,
                "the ledger holds no record to perturb, so the independence probe could "
                "not establish that the reference is not derived from it",
            )
        )
        return refusals, unproven
    if dict(source.views(perturbed)) == dict(baseline):
        return refusals, unproven
    if dict(source.views(ledger_events)) != dict(baseline):
        unproven.append(
            Inconclusive(
                RULE_DERIVED_FROM_LEDGER,
                "the reference answered two reads of the *unperturbed* ledger differently, "
                "so it moved on its own and the probe could not attribute the movement",
            )
        )
        return refusals, unproven
    refusals.append(
        Refusal(
            RULE_DERIVED_FROM_LEDGER,
            f"the reference's answers moved when one synthetic event was added to the "
            f"owned ledger and held still without it, so it is a function of that ledger "
            f"rather than an independent source: {LOSSY_SNAPSHOT_REASON}",
        )
    )
    return refusals, unproven


# --- the comparison -----------------------------------------------------------


@dataclass(frozen=True)
class Disagreement:
    """One query on which the two stores gave different answers about one record."""

    record: str
    query: str
    owned: Any
    reference: Any


@dataclass
class DifferentialReport:
    """What the differential found, and what it could not establish.

    Attributes:
        records: Records the owned ledger holds.
        compared: Records both sides answered for.
        disagreements: Every query on which the two differed, by record then query order.
        unanswered: Records the owned ledger holds *live* that the reference did not answer
            for. A finding, not a filter: a reference that answers for a subset would
            otherwise report clean by saying less (basicly-vkh0's own "a filter on an
            optional field hides a population"). A tombstoned record is the one exclusion,
            and it is the opposite case — the two stores spell one deletion differently
            rather than disagreeing about it, so counting it here would make every ledger
            carrying a tombstone permanently unclean and no clean report would ever license
            the flip.
        unknown: Records the reference answered for that the ledger does not hold.
        refusals: Reasons the reference is not the live tracker. Any one of these voids
            the comparison rather than qualifying it.
        inconclusive: Queries whose answers were constant across the population, so
            agreement on them is the absence of evidence rather than evidence.
    """

    records: int = 0
    compared: int = 0
    disagreements: list[Disagreement] = field(default_factory=list)
    unanswered: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    refusals: list[Refusal] = field(default_factory=list)
    inconclusive: list[Inconclusive] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """The two stores agreed on every query, for every record, and may be trusted to.

        Every one of the five findings is disqualifying, and the refusals most of all: a
        differential run against a derivative of the owned ledger is not a weaker result
        than one run against the live tracker, it is not a result.
        """
        return not (self.disagreements or self.unanswered or self.unknown or self.refusals)

    @property
    def conclusive(self) -> bool:
        """Every query discriminated something, so a clean report is evidence.

        Separate from :attr:`clean` on purpose. A caller deciding whether the flip
        (basicly-vkh0.19) is licensed has to ask both, and a single boolean would let the
        weaker question stand in for the stronger one.
        """
        return not self.inconclusive

    def summary(self) -> str:
        """One line per finding class, for a caller reporting the run to a human."""
        lines = [f"{self.compared} of {self.records} record(s) compared on {', '.join(QUERIES)}"]
        lines += [f"  refused: {refusal.rule}: {refusal.detail}" for refusal in self.refusals]
        lines += [
            f"  {item.record} {item.query}: owned {item.owned!r} != reference {item.reference!r}"
            for item in self.disagreements
        ]
        lines += [f"  unanswered by the reference: {record}" for record in self.unanswered]
        lines += [f"  unknown to the ledger: {record}" for record in self.unknown]
        lines += [f"  inconclusive on {item.subject}: {item.reason}" for item in self.inconclusive]
        return "\n".join(lines)


def _constant_queries(
    owned: Mapping[str, Verdict], reference: Mapping[str, Verdict], compared: Sequence[str]
) -> list[Inconclusive]:
    """Queries whose answers never varied across the compared population.

    The vacuity check, and it is not hypothetical: on the tracker this was built against
    every record reported zero gate rows, so the gate query is constant and a report saying
    ``clean`` would be reporting the absence of evidence as agreement.
    """
    found: list[Inconclusive] = []
    for query in QUERIES:
        seen = {owned[record].answer(query) for record in compared}
        seen |= {reference[record].answer(query) for record in compared}
        if len(seen) <= 1:
            answer = next(iter(seen)) if seen else None
            found.append(
                Inconclusive(
                    query,
                    f"every compared record answered {answer!r}, so agreement on this "
                    f"query discriminated nothing",
                )
            )
    return found


def compare(
    owned: Mapping[str, RecordView],
    reference: Mapping[str, RecordView],
    vocabulary: Vocabulary = DEFAULT_VOCABULARY,
) -> DifferentialReport:
    """Compare two stores' record views on all three queries, without auditing either.

    The pure half, exposed so a caller can diff two sets of views it already holds.
    :func:`run_differential` is the one that refuses a reference that is not live, and it is
    the entry point §5's step 2 means.

    Both sides are derived by :func:`verdicts` over their **own whole population**, not over
    the intersection: the ready set is a property of the graph, so restricting the reference
    to the records the ledger holds would silently satisfy a blocking edge whose target the
    reference alone knows about.

    A tombstoned owned record the reference is silent about is the two stores spelling one
    deletion differently, so it is not reported as unanswered — see
    :attr:`DifferentialReport.unanswered`. One the reference *does* answer for stays in the
    comparison, because that is the two stores disagreeing about whether the record exists,
    and :func:`is_ready` makes it visible as a ``ready`` disagreement.
    """
    owned_verdicts = verdicts(owned, vocabulary)
    reference_verdicts = verdicts(reference, vocabulary)
    compared = sorted(set(owned_verdicts) & set(reference_verdicts))
    deleted = {record for record, view in owned.items() if view.tombstoned}
    report = DifferentialReport(
        records=len(owned_verdicts),
        compared=len(compared),
        unanswered=sorted(set(owned_verdicts) - set(reference_verdicts) - deleted),
        unknown=sorted(set(reference_verdicts) - set(owned_verdicts)),
    )
    for record in compared:
        for query in QUERIES:
            mine = owned_verdicts[record].answer(query)
            theirs = reference_verdicts[record].answer(query)
            if mine != theirs:
                report.disagreements.append(Disagreement(record, query, mine, theirs))
    report.inconclusive = _constant_queries(owned_verdicts, reference_verdicts, compared)
    return report


def run_differential(
    directory: Path | str,
    source: ReferenceSource,
    vocabulary: Vocabulary = DEFAULT_VOCABULARY,
) -> DifferentialReport:
    """Run the shadow differential for the ledger at *directory* against *source*.

    The audit runs **before the comparison**, and its findings are carried on the report
    rather than raised, because the point of §5.1's rule is that a self-agreeing comparison
    *looks* clean: a caller that only ever read :attr:`DifferentialReport.disagreements`
    would still see the refusal in :attr:`clean`, and one that reports the run to a human
    sees the reason.

    The comparison is run even when the reference is refused. That is deliberate and is the
    whole demonstration: the two sides agree on every query the snapshot can express, and
    the report says in the same breath that the agreement proves nothing.
    """
    ledger_events = read_ledger(directory)
    baseline = dict(source.views(ledger_events))
    refusals, unproven = audit_reference(source, ledger_events, baseline, vocabulary)
    report = compare(views_from_events(ledger_events), baseline, vocabulary)
    report.refusals = refusals
    report.inconclusive = unproven + report.inconclusive
    return report
