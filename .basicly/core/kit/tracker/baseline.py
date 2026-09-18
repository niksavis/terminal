from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

IMPORT_MARKER = "imported_from"

ADOPTION_SOURCE = "hand-write-adoption"

KIND_CREATED = "created"

BASELINE_FILE = "differential-baseline.json"

SCOPE_SUBJECT = "scope"


class BaselineError(Exception):
    pass


@dataclass(frozen=True)
class Baseline:
    records: frozenset[str] = frozenset()
    declared: str = ""

    @property
    def declared_at(self) -> str:
        return self.declared or "no date recorded"


@dataclass
class ScopedReport:
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
        return not (self.disagreements or self.undeclared or self.refusals)

    @property
    def conclusive(self) -> bool:
        return not self.inconclusive

    def summary(self) -> str:
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

    found: dict[str, str] = {}
    for event in ledger_events:
        payload = _mapping(_attr(event, "payload"))
        marker = payload.get(IMPORT_MARKER)
        if _attr(event, "kind") == KIND_CREATED and marker:
            found[str(_attr(event, "record"))] = str(marker)
    return found


def imported_records(ledger_events: Iterable[Any]) -> frozenset[str]:
    return frozenset(
        record for record, source in origins(ledger_events).items() if source != ADOPTION_SOURCE
    )


def adopted_records(ledger_events: Iterable[Any]) -> frozenset[str]:
    return frozenset(
        record for record, source in origins(ledger_events).items() if source == ADOPTION_SOURCE
    )


def read_baseline(directory: Path | str) -> Baseline:

    path = Path(directory) / BASELINE_FILE
    if not path.is_file():
        return Baseline()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Baseline(frozenset(str(x) for x in payload["records"]), str(payload["declared"]))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise BaselineError(f"{path} is present and unreadable: {error}") from error


def write_baseline(directory: Path | str, records: Iterable[str], declared: str) -> Baseline:

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
    if not dual_written:
        return (
            f"{SCOPE_SUBJECT}: 0 post-flip record(s) reached the ledger through the dual "
            "write, so agreement is the absence of evidence rather than evidence",
        )
    return ()


def _ledger_records(ledger_events: Iterable[Any]) -> set[str]:
    return {str(_attr(event, "record")) for event in ledger_events}


def _attr(event: Any, name: str) -> Any:
    if isinstance(event, Mapping):
        return event.get(name)
    return getattr(event, name, None)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
