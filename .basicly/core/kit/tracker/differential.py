from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

_HERE = Path(__file__).resolve().parent
_MIGRATE_MODULE_NAME = "basicly_tracker_kit_migrate"
_SHAPING_MODULE_NAME = "basicly_tracker_kit_shaping"


def _load_migrate() -> ModuleType:

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


def _load_shaping():
    cached = sys.modules.get(_SHAPING_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_SHAPING_MODULE_NAME, _HERE / "shaping.py")
    if spec is None or spec.loader is None:
        raise DifferentialError(
            "the tracker kit's shaping.py is missing from beside differential.py"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_SHAPING_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


migrate = _load_migrate()
events = migrate.events
shaping = _load_shaping()

_DERIVATION_MODULE_NAME = "basicly_tracker_kit_derivation"


def _load_derivation() -> ModuleType:

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

_EDGE_KEYS = provenance.labels.DIALECT_KEYS


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


KIND_GATE = events.KIND_GATE
GATE_NAME_KEY = "gate"
GATE_PROVIDER_KEY = "provider"
GATE_PASSED_KEY = "passed"


RULE_REIMPORTED_EXPORT = "reimported-own-export"
RULE_EXPORT_BACKED = "export-backed-reference"
RULE_DERIVED_FROM_LEDGER = "derived-from-owned-ledger"

LOSSY_SNAPSHOT_REASON = (
    "two derivatives of one lossy snapshot agree with each other and prove nothing"
)

EXPORT_CANNOT_EXPRESS = (
    "a gate-report row is visible to a live gate query and absent from the JSONL export, so an "
    "export-backed reference cannot answer the gate-status query at all"
)


def views_from_events(ledger_events: Iterable[Any]) -> dict[str, RecordView]:

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

    keys = _EDGE_KEYS[provenance.edge_dialect(payload)]
    return payload.get(keys[0]), payload.get(keys[1])


def edge_dialects(ledger_events: Iterable[Any]) -> tuple[str, ...]:

    seen = {
        provenance.edge_dialect(event.payload)
        for event in ledger_events
        if getattr(event, "kind", "") in (migrate.KIND_EDGE, events.KIND_EDGE_RETRACTED)
    }
    return tuple(sorted(seen))


def read_ledger(directory: Path | str) -> list[Any]:

    found, _ = events.read_events(directory)
    return found


@dataclass(frozen=True)
class ReferenceSource:
    views: Callable[[Sequence[Any]], Mapping[str, RecordView]]
    snapshot: str | None = None


@dataclass(frozen=True)
class Refusal:
    rule: str
    detail: str


@dataclass(frozen=True)
class Inconclusive:
    subject: str
    reason: str


def imported_digests(ledger_events: Iterable[Any]) -> frozenset[str]:

    found: set[str] = set()
    for event in ledger_events:
        if event.kind != events.KIND_CREATED:
            continue
        digest = event.payload.get(migrate.DIGEST_KEY)
        if isinstance(digest, str) and digest:
            found.add(digest)
    return frozenset(found)


def probe_events(ledger_events: Sequence[Any], vocabulary: Vocabulary) -> list[Any]:

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


@dataclass(frozen=True)
class Disagreement:
    record: str
    query: str
    owned: Any
    reference: Any


@dataclass
class DifferentialReport:
    records: int = 0
    compared: int = 0
    disagreements: list[Disagreement] = field(default_factory=list)
    unanswered: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    refusals: list[Refusal] = field(default_factory=list)
    inconclusive: list[Inconclusive] = field(default_factory=list)

    @property
    def clean(self) -> bool:

        return not (self.disagreements or self.unanswered or self.unknown or self.refusals)

    @property
    def conclusive(self) -> bool:

        return not self.inconclusive

    def summary(self) -> str:
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

    ledger_events = read_ledger(directory)
    baseline = dict(source.views(ledger_events))
    refusals, unproven = audit_reference(source, ledger_events, baseline, vocabulary)
    report = compare(views_from_events(ledger_events), baseline, vocabulary)
    report.refusals = refusals
    report.inconclusive = unproven + report.inconclusive
    return report
