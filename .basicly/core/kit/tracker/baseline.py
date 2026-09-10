"""The flip boundary: which records the shadow differential may be judged on.

Step 2 of the cutover (§5 in `SPEC.md`) proves **the dual write agrees**, not that
history agrees. `basicly-c357` records why both open records about the same gap were right —
a consumer needs a re-runnable import (`vkh0.23`), and closing this repo's historical gap
by re-importing would leave the owned side tracking the external one (`u4xu`).

A record the **ledger** holds is classified by the marker its own producer wrote, so no
flip point has to be kept in step with the tree: ``migrate.py`` stamps every extracted
event with :data:`IMPORT_MARKER`, and the repair for a record created **by hand**
(`basicly-vkh0.24`) stamps :data:`ADOPTION_SOURCE` — in scope and judged, but
evidence for nothing, because the dual write never touched it. A record the **reference**
holds and the ledger does not has no ledger event to classify, so it needs the declared
baseline below. That set can only shrink — a dual write puts every new record on both
sides — so an unknown id outside it is a real failure rather than more history.

An in-scope population with nothing the dual write put there is **inconclusive, never
clean**: scoping leaves it empty until the flip happens, and reporting that as clean would
license the next rung on a comparison that discriminated nothing.

Nothing here reads a clock. The declaration stamp is caller-supplied evidence (§9.5).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# `migrate.SOURCE_KEY`, spelled rather than imported so this module stays a leaf: it is a
# wire format both sides already agreed on.
IMPORT_MARKER = "imported_from"

# The one :data:`IMPORT_MARKER` value that does not mean history (basicly-vkh0.24): a label
# rather than a second key, so the classifier stays one read of one marker.
ADOPTION_SOURCE = "hand-write-adoption"

# The created-event kind, likewise spelled rather than imported (`events.KIND_CREATED`).
KIND_CREATED = "created"

# The declared baseline, committed beside the ledger it describes. JSON rather than TOML
# because it is generated and never hand-edited, and it sits in the ledger directory
# because it is a fact about that ledger's history, not a preference.
BASELINE_FILE = "differential-baseline.json"

# The subject an empty-scope finding is reported under, as `differential.Inconclusive`.
SCOPE_SUBJECT = "scope"


class BaselineError(Exception):
    """The declared baseline is present and unreadable.

    Raised rather than defaulted to empty, which would turn every historical record into
    a finding — this module's own failure, reached by another route.
    """


@dataclass(frozen=True)
class Baseline:
    """The historical delta, declared once and subtracted from every later run.

    Attributes:
        records: Ids the reference held and the ledger did not, at declaration time.
        declared: When it was declared, as evidence. Nothing branches on it.
    """

    records: frozenset[str] = frozenset()
    declared: str = ""

    @property
    def declared_at(self) -> str:
        """The stamp to print, or a phrase saying none was recorded."""
        return self.declared or "no date recorded"


@dataclass
class ScopedReport:
    """A differential report split into what it may be judged on and what it may not.

    Wraps rather than extends ``DifferentialReport``, so the comparison keeps working
    unchanged for a caller that wants no scoping.

    Attributes:
        in_scope: Records created after the flip; the verdict is computed over these.
        history: Ledger records extracted from the export at the flip.
        adopted: In-scope records the repair brought in rather than the dual write. Judged
            like the rest, evidence for nothing: a reconciled record agrees because it was
            reconciled.
        baseline: Declared ids the reference holds and the ledger does not.
        undeclared: Unknown ids outside the baseline — a real dual-write failure.
        refusals: Reasons the reference is not the live tracker, carried through
            unscoped: a refusal voids the comparison, and the flip boundary is about
            which records are judged, never about whether the reference was real.
        disagreements: In-scope disagreements, the only ones that make a run unclean.
        excused: Disagreements on historical records, reported and never judged.
        inconclusive: Why a clean verdict here would not be evidence.
    """

    in_scope: tuple[str, ...] = ()
    history: tuple[str, ...] = ()
    adopted: tuple[str, ...] = ()
    baseline: Baseline = field(default_factory=Baseline)
    undeclared: tuple[str, ...] = ()
    refusals: tuple[Any, ...] = ()
    disagreements: tuple[Any, ...] = ()
    excused: tuple[Any, ...] = ()
    inconclusive: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        """Nothing in scope disagreed, nothing is undeclared, and the reference was real."""
        return not (self.disagreements or self.undeclared or self.refusals)

    @property
    def conclusive(self) -> bool:
        """A clean verdict here is evidence rather than the absence of it."""
        return not self.inconclusive

    def summary(self) -> str:
        """One line per finding class, for a caller reporting the run to a human."""
        lines = [
            f"{len(self.in_scope)} record(s) in scope, {len(self.adopted)} of them adopted; "
            f"{len(self.history)} imported, {len(self.baseline.records)} declared "
            f"({self.baseline.declared_at})"
        ]
        lines += [f"  refused: {item}" for item in self.refusals]
        lines += [f"  disagreement: {item}" for item in self.disagreements]
        lines += [
            f"  undeclared and absent from the ledger: {record}" for record in self.undeclared
        ]
        lines += [f"  excused as history: {item}" for item in self.excused]
        lines += [f"  inconclusive: {reason}" for reason in self.inconclusive]
        return "\n".join(lines)


def origins(ledger_events: Iterable[Any]) -> dict[str, str]:
    """Each record's import label, for the records whose ``created`` event carries one.

    Keyed on that event alone, because a record's origin is a fact about how it began.
    """
    found: dict[str, str] = {}
    for event in ledger_events:
        payload = _mapping(_attr(event, "payload"))
        marker = payload.get(IMPORT_MARKER)
        if _attr(event, "kind") == KIND_CREATED and marker:
            found[str(_attr(event, "record"))] = str(marker)
    return found


def imported_records(ledger_events: Iterable[Any]) -> frozenset[str]:
    """Every record extracted from the export at the flip — the history population."""
    return frozenset(
        record for record, source in origins(ledger_events).items() if source != ADOPTION_SOURCE
    )


def adopted_records(ledger_events: Iterable[Any]) -> frozenset[str]:
    """Every record the hand-write repair brought in, which is history to nobody."""
    return frozenset(
        record for record, source in origins(ledger_events).items() if source == ADOPTION_SOURCE
    )


def read_baseline(directory: Path | str) -> Baseline:
    """The declared baseline for the ledger at *directory*, empty when none is declared.

    Raises:
        BaselineError: the file exists and does not parse, or is not the shape written.
    """
    path = Path(directory) / BASELINE_FILE
    if not path.is_file():
        return Baseline()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Baseline(frozenset(str(x) for x in payload["records"]), str(payload["declared"]))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise BaselineError(f"{path} is present and unreadable: {error}") from error


def write_baseline(directory: Path | str, records: Iterable[str], declared: str) -> Baseline:
    """Declare *records* as the historical delta for the ledger at *directory*.

    A second declaration is refused, and that refusal is the control the boundary rests
    on: re-declaring after a dual write has begun absorbs a genuine failure into history
    and reports the run clean. The set may only shrink, so widening it is never a repair.

    Raises:
        BaselineError: a baseline is already declared for this ledger.
    """
    existing = read_baseline(directory)
    if existing.records or existing.declared:
        raise BaselineError(
            f"a baseline of {len(existing.records)} record(s) is already declared "
            f"({existing.declared_at}); re-declaring would absorb a dual-write failure "
            "into history"
        )
    baseline = Baseline(frozenset(str(record) for record in records), declared)
    payload = {"declared": baseline.declared, "records": sorted(baseline.records)}
    path = Path(directory) / BASELINE_FILE
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return baseline


def scope(report: Any, ledger_events: Sequence[Any], baseline: Baseline) -> ScopedReport:
    """Split *report* into what the flip boundary admits and what it excuses.

    A disagreement on an imported record is excused rather than dropped, because the
    reason those 375 rows differ is that no export carries a gate field for the import to
    have read — an absence of evidence rather than a dual-write disagreement, and one no
    amount of re-importing would fix.

    An **adopted** record is excused from nothing; it is subtracted only from the
    population conclusiveness is asked of.
    """
    history = imported_records(ledger_events)
    adopted = adopted_records(ledger_events)
    in_scope = sorted(_ledger_records(ledger_events) - history)
    excused = tuple(item for item in report.disagreements if str(_attr(item, "record")) in history)
    live = tuple(item for item in report.disagreements if str(_attr(item, "record")) not in history)
    undeclared = tuple(sorted(set(report.unknown) - baseline.records))
    return ScopedReport(
        in_scope=tuple(in_scope),
        history=tuple(sorted(history)),
        adopted=tuple(sorted(adopted)),
        baseline=baseline,
        undeclared=undeclared,
        refusals=tuple(getattr(report, "refusals", ()) or ()),
        disagreements=live,
        excused=excused,
        inconclusive=_unproven([record for record in in_scope if record not in adopted]),
    )


def _unproven(dual_written: Sequence[str]) -> tuple[str, ...]:
    """Why a clean verdict would not be evidence, empty when it would be."""
    if not dual_written:
        return (
            f"{SCOPE_SUBJECT}: 0 post-flip record(s) reached the ledger through the dual "
            "write, so agreement is the absence of evidence rather than evidence",
        )
    return ()


def _ledger_records(ledger_events: Iterable[Any]) -> set[str]:
    """Every record id the ledger holds an event for."""
    return {str(_attr(event, "record")) for event in ledger_events}


def _attr(event: Any, name: str) -> Any:
    """Read *name* off an event, whether it is a mapping or an object."""
    if isinstance(event, Mapping):
        return event.get(name)
    return getattr(event, name, None)


def _mapping(value: Any) -> Mapping[str, Any]:
    """*value* as a mapping, empty when it is not one."""
    return value if isinstance(value, Mapping) else {}
