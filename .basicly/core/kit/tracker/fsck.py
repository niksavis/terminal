from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside fsck.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


snapshot = _load("snapshot.py", "basicly_tracker_kit_snapshot")
migrate = _load("migrate.py", "basicly_tracker_kit_migrate")
provenance = _load("provenance.py", "basicly_tracker_kit_provenance")
label_shape = _load("label_shape.py", "basicly_tracker_kit_label_shape")
forks = _load("forks.py", "basicly_tracker_kit_forks")
events = snapshot.events


EDGE_KINDS = frozenset({migrate.KIND_EDGE, provenance.KIND_EDGE})
EDGE_RECORD_KEYS = tuple(sorted({migrate.EDGE_FROM, migrate.EDGE_TO, provenance.KEY_TARGET}))


BROKEN = "broken"
DERIVED = "derived"
WARNING = "warning"

EXIT_CLEAN = 0
EXIT_DERIVED = 1
EXIT_BROKEN = 2


UNPARSEABLE = "unparseable"
MALFORMED = "malformed"
FORKED_SEQUENCE = "forked-sequence"
CONFLICTING_FORK = "conflicting-fork"
SEQUENCE_GAP = "sequence-gap"
DUPLICATE_ID = "duplicate-id"
DANGLING_RECORD = "dangling-record"
DANGLING_EDGE = "dangling-edge"
CARRIED_TOTALS = "carried-totals"
DERIVED_UNREADABLE = "derived-unreadable"
DERIVED_DISAGREES = "derived-disagrees"
UNFOLDED_KIND = "unfolded-kind"
UNMINTED_ID = "unminted-id"
WITHDRAWAL_UNRECORDED = "withdrawal-unrecorded"
WITHDRAWAL_UNAPPLIED = "withdrawal-unapplied"
WITHDRAWAL_RESURRECTED = "withdrawal-resurrected"
SPLIT_LABEL = "split-label"
SHARD_BACKLOG = "shard-backlog"

MAX_EVENT_IDS_REPORTED = 10

SHARDS_WARN_ABOVE = 1000
SHARDS_REFUSE_ABOVE = 10000


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str
    subject: str
    detail: str
    event_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        shown = self.event_ids[:MAX_EVENT_IDS_REPORTED]
        form: dict[str, object] = {
            "kind": self.kind,
            "severity": self.severity,
            "subject": self.subject,
            "detail": self.detail,
            "event_ids": list(shown),
        }
        if len(shown) < len(self.event_ids):
            form["event_ids_omitted"] = len(self.event_ids) - len(shown)
        return form


@dataclass(frozen=True)
class Report:
    directory: Path
    findings: tuple[Finding, ...] = ()
    events: int = 0
    records: int = 0
    delegated_kinds: tuple[tuple[str, int, str], ...] = ()
    unattributed: int = 0

    def of_severity(self, severity: str) -> tuple[Finding, ...]:
        return tuple(found for found in self.findings if found.severity == severity)

    @property
    def clean(self) -> bool:
        return not self.of_severity(BROKEN) and not self.of_severity(DERIVED)

    @property
    def exit_code(self) -> int:
        if self.of_severity(BROKEN):
            return EXIT_BROKEN
        if self.of_severity(DERIVED):
            return EXIT_DERIVED
        return EXIT_CLEAN

    def as_dict(self) -> dict[str, object]:
        return {
            "directory": str(self.directory),
            "clean": self.clean,
            "exit_code": self.exit_code,
            "events": self.events,
            "records": self.records,
            "broken": len(self.of_severity(BROKEN)),
            "derived": len(self.of_severity(DERIVED)),
            "warnings": len(self.of_severity(WARNING)),
            "findings": [found.as_dict() for found in self.findings],
            "unattributed": self.unattributed,
            "delegated_kinds": {
                kind: {"events": count, "folded_by": owner}
                for kind, count, owner in self.delegated_kinds
            },
        }


def derive(paths: Sequence[Path]) -> Any:

    tally = snapshot.scan_paths(paths)
    found: list[Any] = []
    for path in paths:
        parsed, _ = events.read_log(path)
        found.extend(parsed)
    return snapshot.Snapshot(
        header=snapshot.Header(
            last_event_id=tally.last_event_id,
            event_count=len(found),
            log_lines=tally.lines,
        ),
        records=dict(events.fold(found).records),
    )


def covered_logs(directory: Path | str, boundary: str) -> list[Path]:

    return [path for path in events.log_paths(directory) if snapshot.period_of(path) <= boundary]


def derived_targets(directory: Path | str) -> list[tuple[Path, list[Path]]]:

    ledger = Path(directory)
    logs = events.log_paths(ledger)
    targets: list[tuple[Path, list[Path]]] = []
    for closed in logs[:-1]:
        boundary = snapshot.period_of(closed)
        targets.append((snapshot.checkpoint_path(ledger, boundary), covered_logs(ledger, boundary)))
    targets.append((snapshot.snapshot_path(ledger), events.ledger_paths(ledger)))
    return targets


def _malformed(collected: Sequence[Any]) -> list[tuple[int, Any, str]]:

    refused: list[tuple[int, Any, str]] = []
    for position, event in enumerate(collected):
        try:
            events.fold([event])
        except events.InvalidEventError as exc:
            refused.append((position, event, str(exc)))
    return refused


def _unparseable_findings(quarantined: Iterable[Any]) -> list[Finding]:
    return [
        Finding(
            kind=UNPARSEABLE,
            severity=BROKEN,
            subject=f"{bad.path.name}:{bad.line_number}",
            detail=(
                f"the line is not an event and was written whole, so it is interior garbage "
                f"wherever it sits: {bad.reason}"
            ),
        )
        for bad in quarantined
    ]


def _malformed_findings(malformed: Iterable[tuple[int, Any, str]]) -> list[Finding]:
    return [
        Finding(
            kind=MALFORMED,
            severity=BROKEN,
            subject=event.record,
            detail=(
                f"a {event.kind} event carries a payload that kind cannot mean, so every fold "
                f"of this ledger refuses it: {reason}"
            ),
            event_ids=(event.id,),
        )
        for _, event, reason in malformed
    ]


def _fork_findings(ordered: Sequence[Any]) -> list[Finding]:

    clashes = forks.conflicts(ordered)
    clashing = {(one.record, one.seq) for one in clashes}
    findings = [
        Finding(
            kind=CONFLICTING_FORK,
            severity=BROKEN,
            subject=one.record,
            detail=(
                f"two branches set {one.key} to {', '.join(one.values)} at sequence {one.seq}, "
                f"so the value is a tie broken by id; choose it with update, or keep the "
                f"current value with resolve"
            ),
        )
        for one in clashes
    ]
    findings += [
        Finding(
            kind=FORKED_SEQUENCE,
            severity=WARNING,
            subject=record,
            detail=(
                f"{len(group)} writers appended sequence {seq} on this record from different "
                f"branches; nothing they set conflicts"
            ),
            event_ids=tuple(sorted(event.id for event in group)),
        )
        for (record, seq), group in sorted(forks.forked_groups(ordered).items())
        if (record, seq) not in clashing
    ]
    return findings


def sequence_gaps(ordered: Sequence[Any]) -> dict[str, tuple[int, ...]]:

    seen: dict[str, set[int]] = {}
    for event in ordered:
        seen.setdefault(event.record, set()).add(event.seq)
    gaps = {}
    for record, claimed in seen.items():
        missing = tuple(sorted(set(range(1, max(claimed) + 1)) - claimed))
        if missing:
            gaps[record] = missing
    return gaps


def _gap_findings(gaps: Mapping[str, tuple[int, ...]]) -> list[Finding]:

    return [
        Finding(
            kind=SEQUENCE_GAP,
            severity=BROKEN,
            subject=record,
            detail=(
                f"no event claims sequence {', '.join(str(seq) for seq in missing)} on this "
                f"record, and §4.1's writer assigns max+1, so a line that was written is gone; "
                f"the carried totals of every later event on it are void until a fold restates "
                f"them"
            ),
            event_ids=(),
        )
        for record, missing in sorted(gaps.items())
    ]


def _duplicate_id_findings(collected: Sequence[Any]) -> list[Finding]:

    lines: dict[str, list[Any]] = {}
    for event in collected:
        lines.setdefault(event.id, []).append(event)
    findings = []
    for event_id, found in sorted(lines.items()):
        if len(found) < 2:
            continue
        content = {(one.record, one.seq, one.kind, _dumps(one.payload)) for one in found}
        if len(content) < 2:
            continue
        findings.append(
            Finding(
                kind=DUPLICATE_ID,
                severity=BROKEN,
                subject=event_id,
                detail=(
                    f"{len(found)} lines share this id and {len(content)} of them disagree about "
                    f"the record, sequence, kind or payload it names, so the fold keeps one of "
                    f"them by canonical order rather than by evidence"
                ),
                event_ids=(event_id,),
            )
        )
    return findings


def _reference_findings(ordered: Sequence[Any]) -> list[Finding]:

    created = {event.record for event in ordered if event.kind == events.KIND_CREATED}
    uncreated: dict[str, list[str]] = {}
    dangling: dict[str, list[str]] = {}
    for event in ordered:
        if event.record not in created:
            uncreated.setdefault(event.record, []).append(event.id)
        if event.kind not in EDGE_KINDS:
            continue
        for key in EDGE_RECORD_KEYS:
            target = event.payload.get(key)
            if isinstance(target, str) and target not in created:
                dangling.setdefault(target, []).append(event.id)
    findings = [
        Finding(
            kind=DANGLING_RECORD,
            severity=BROKEN,
            subject=record,
            detail=(
                "no created event ever minted this record and the events listed here are about "
                "it, so the fold invents a record the log never opened"
            ),
            event_ids=tuple(sorted(set(found))),
        )
        for record, found in sorted(uncreated.items())
    ]
    findings.extend(
        Finding(
            kind=DANGLING_EDGE,
            severity=BROKEN,
            subject=target,
            detail=(
                "no created event ever minted this record and the edges listed here point at "
                "it, so a landing would be gated on a record that cannot exist"
            ),
            event_ids=tuple(sorted(set(found))),
        )
        for target, found in sorted(dangling.items())
        if target not in uncreated
    )
    return findings


def _totals_findings(folded: Any, ordered: Sequence[Any], voided: Iterable[str]) -> list[Finding]:

    excluded = set(voided)
    record_of = {event.id: event.record for event in ordered}
    return [
        Finding(
            kind=CARRIED_TOTALS,
            severity=BROKEN,
            subject=record_of[event_id],
            detail=(
                "the totals this event carries disagree with the fold, which is the authority; "
                "the cache is a finding here and never a repair in place"
            ),
            event_ids=(event_id,),
        )
        for event_id in sorted(set(folded.mismatched_totals))
        if event_id in record_of and record_of[event_id] not in excluded
    ]


def _unfolded_kind_findings(folded: Any, ordered: Sequence[Any]) -> list[Finding]:

    carriers: dict[str, list[str]] = {}
    for event in ordered:
        if event.kind in folded.unknown_kinds:
            carriers.setdefault(event.kind, []).append(event.id)
    return [
        Finding(
            kind=UNFOLDED_KIND,
            severity=WARNING,
            subject=kind,
            detail=(
                f"no module in this kit folds this kind, carried on {count} of this ledger's "
                f"lines: a newer writer's, or a malformed one. Preserved verbatim and warned "
                f"about, because an old reader hitting a newer ledger must not report false "
                f"corruption"
            ),
            event_ids=tuple(sorted(carriers.get(kind, ()))),
        )
        for kind, count in sorted(folded.unknown_kinds.items())
    ]


def _minted_at_some_generation(event: Any, bound: int) -> bool:

    for generation in range(1, bound + 1):
        if event.id == events.event_id_for(
            event.record, event.kind, event.payload, generation=generation
        ):
            return True
    return False


def _unminted_id_findings(ordered: Sequence[Any]) -> list[Finding]:

    per_record: dict[str, int] = {}
    for event in ordered:
        per_record[event.record] = per_record.get(event.record, 0) + 1
    findings = []
    for event in ordered:
        if not events.ids.is_record_id(event.record):
            continue
        if _minted_at_some_generation(event, per_record[event.record]):
            continue
        findings.append(
            Finding(
                kind=UNMINTED_ID,
                severity=BROKEN,
                subject=event.id,
                detail=(
                    "this id is not the one the record, kind and payload on this line mint, so "
                    "the line was rewritten in place by something other than the withdrawal "
                    "path, which re-mints"
                ),
                event_ids=(event.id,),
            )
        )
    return findings


def _withdrawal_findings(ordered: Sequence[Any]) -> list[Finding]:

    present = {event.id for event in ordered}
    marked = {
        event.id: event.payload[events.WITHDRAWN_FROM]
        for event in ordered
        if events.WITHDRAWN_FROM in event.payload
    }
    audited: dict[str, str] = {}
    for event in ordered:
        if event.kind != events.KIND_WITHDRAWN:
            continue
        target = event.payload.get(events.WITHDRAWN_TARGET)
        if isinstance(target, str):
            audited[target] = event.id
    findings = [
        Finding(
            kind=WITHDRAWAL_UNRECORDED,
            severity=BROKEN,
            subject=event_id,
            detail=(
                f"this payload says content was withdrawn and no {events.KIND_WITHDRAWN} event "
                f"names it, so the rewrite has no reason and no time recorded"
            ),
            event_ids=(event_id,),
        )
        for event_id in sorted(set(marked) - set(audited))
    ]
    findings += [
        Finding(
            kind=WITHDRAWAL_UNAPPLIED,
            severity=BROKEN,
            subject=event_id,
            detail=(
                "a withdrawal names this event as the content it took out and the log holds no "
                "such event, so the trail is evidence of a rewrite that is not here"
            ),
            event_ids=(audited[event_id],),
        )
        for event_id in sorted(set(audited) - present)
    ]
    return findings + [
        Finding(
            kind=WITHDRAWAL_RESURRECTED,
            severity=BROKEN,
            subject=str(retired),
            detail=(
                f"{event_id} withdrew this event's content and the retired line is in the log "
                f"again, so a merge of a branch written before the withdrawal made it readable"
            ),
            event_ids=(str(retired), event_id),
        )
        for event_id, retired in sorted(marked.items())
        if isinstance(retired, str) and retired in present
    ]


def _split_label_findings(ordered: Sequence[Any]) -> list[Finding]:

    return [
        Finding(
            kind=SPLIT_LABEL,
            severity=BROKEN,
            subject=record,
            detail=(
                f"a label write names {len(labels)} label(s) of one character "
                f"({', '.join(repr(label) for label in labels)}) — what a string iterated "
                f"instead of split leaves behind. Clear it with a corrective write"
            ),
            event_ids=event_ids,
        )
        for record, labels, event_ids in label_shape.split_labels(ordered)
    ]


def _delegated_census(folded: Any) -> tuple[tuple[str, int, str], ...]:

    return tuple(
        (kind, count, events.DELEGATED_KINDS[kind])
        for kind, count in sorted(folded.delegated_kinds.items())
    )


def _disagreement(present: Any, expected: Any) -> str:
    parts = []
    if present.header != expected.header:
        parts.append(
            f"its header folded {present.header.event_count} events under tip "
            f"{present.header.last_event_id!r} and the log gives {expected.header.event_count} "
            f"under {expected.header.last_event_id!r}"
        )
    differing = sorted(
        record
        for record in set(present.records) | set(expected.records)
        if present.records.get(record) != expected.records.get(record)
    )
    if differing:
        shown = ", ".join(differing[:5])
        more = "" if len(differing) <= 5 else f" and {len(differing) - 5} more"
        parts.append(f"{len(differing)} records differ ({shown}{more})")
    return "; ".join(parts) if parts else "it differs from the fold"


def _derived_findings(directory: Path | str) -> list[Finding]:

    findings = []
    for path, covered in derived_targets(directory):
        try:
            present = snapshot.read_snapshot(path)
        except snapshot.SnapshotError as exc:
            findings.append(
                Finding(
                    kind=DERIVED_UNREADABLE,
                    severity=DERIVED,
                    subject=path.name,
                    detail=f"the file exists and is not a usable derivative: {exc}",
                )
            )
            continue
        if present is None:
            continue
        expected = derive(covered)
        if present.header.log_lines != expected.header.log_lines:
            continue
        if present != expected:
            findings.append(
                Finding(
                    kind=DERIVED_DISAGREES,
                    severity=DERIVED,
                    subject=path.name,
                    detail=(
                        f"its header dates it to the log's current {expected.header.log_lines} "
                        f"lines, so every cheap check reads it as fresh, but "
                        f"{_disagreement(present, expected)}"
                    ),
                )
            )
    return findings


def _shard_findings(directory: Path | str) -> list[Finding]:

    shards = events.pending_paths(directory)
    count = len(shards)
    if count <= SHARDS_WARN_ABOVE:
        return []
    severity = BROKEN if count > SHARDS_REFUSE_ABOVE else WARNING
    return [
        Finding(
            kind=SHARD_BACKLOG,
            severity=severity,
            subject=str(Path(directory)),
            detail=(
                f"{count} uncompacted shard(s) against a warn threshold of "
                f"{SHARDS_WARN_ABOVE} and a refuse threshold of {SHARDS_REFUSE_ABOVE}; "
                f"measured 2026-09-17 on basicly-v5zvsh1, one `git add` over a directory "
                f"of shards costs 2.89s at 1000 files and 35.59s at 10000 on NTFS against "
                f"0.16s and 0.66s on ext4, and the ratio doubles every decade. Run "
                f"`compact` to fold them into the trunk log"
            ),
        )
    ]


def check(directory: Path | str) -> Report:

    ledger = Path(directory)
    found, quarantined = events.read_events(ledger)
    malformed: list[tuple[int, Any, str]] = []
    try:
        folded = events.fold(found)
        sound = list(found)
    except events.InvalidEventError:
        malformed = _malformed(found)
        refused = {position for position, _, _ in malformed}
        sound = [event for position, event in enumerate(found) if position not in refused]
        folded = events.fold(sound)
    ordered = events.canonical_order(sound)
    gaps = sequence_gaps(ordered)
    voided = set(folded.forked) | {event.record for _, event, _ in malformed} | set(gaps)

    unattributed = sum(
        1 for event in ordered if not event.actor or event.actor == events.UNATTRIBUTED_ACTOR
    )

    findings = _unparseable_findings(quarantined)
    findings += _malformed_findings(malformed)
    findings += _fork_findings(ordered)
    findings += _gap_findings(gaps)
    findings += _duplicate_id_findings(sound)
    findings += _reference_findings(ordered)
    findings += _unminted_id_findings(ordered)
    findings += _withdrawal_findings(ordered)
    findings += _totals_findings(folded, ordered, voided)
    findings += _unfolded_kind_findings(folded, ordered)
    findings += _split_label_findings(ordered)
    findings += _shard_findings(ledger)
    if not malformed:
        findings += _derived_findings(ledger)
    return Report(
        directory=ledger,
        findings=tuple(findings),
        events=len(ordered),
        records=len(folded.records),
        delegated_kinds=_delegated_census(folded),
        unattributed=unattributed,
    )


@dataclass(frozen=True)
class Rebuild:
    directory: Path
    removed: tuple[Path, ...] = ()
    written: tuple[Path, ...] = ()


def rebuild(directory: Path | str) -> Rebuild:

    ledger = Path(directory)
    if not ledger.is_dir():
        return Rebuild(directory=ledger)
    produced = tuple((path, derive(covered)) for path, covered in derived_targets(ledger))
    for path, proposed in produced:
        loss = snapshot.shrinkage(path, proposed)
        if loss.refused:
            raise snapshot.SnapshotError(f"{path.name}: {loss.reason}")
    removed = tuple(snapshot.derived_paths(ledger))
    for path in removed:
        path.unlink()
    for path, proposed in produced:
        snapshot.write_snapshot(path, proposed)
    return Rebuild(directory=ledger, removed=removed, written=tuple(path for path, _ in produced))


def main(argv: Sequence[str] | None = None) -> int:

    parser = argparse.ArgumentParser(
        description="Check a tracker ledger against its event log, and rebuild its derivatives."
    )
    parser.add_argument("directory", help=f"the ledger directory holding {events.LOG_GLOB}")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="delete every derived file and write it again from the log before checking",
    )
    args = parser.parse_args(argv)
    ledger = Path(args.directory)
    rebuilt: Any = None
    if args.rebuild:
        try:
            rebuilt = rebuild(ledger)
        except events.LedgerError as exc:
            print(_report_json({"directory": str(ledger), "rebuilt": False, "refused": str(exc)}))
            return EXIT_BROKEN
    report = check(ledger).as_dict()
    if rebuilt is not None:
        report["removed"] = [path.name for path in rebuilt.removed]
        report["written"] = [path.name for path in rebuilt.written]
    print(_report_json(report))
    return int(report["exit_code"])  # type: ignore[arg-type]


def _report_json(report: Mapping[str, object]) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False)


def _dumps(obj: Mapping[str, object]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())


def shards_report(directory: Path | str) -> dict[str, object]:

    held = snapshot.events.pending_paths(directory)
    return {
        "count": len(held),
        "writers": [snapshot.events.writer_of(path) for path in held],
        "warn_above": SHARDS_WARN_ABOVE,
        "refuse_above": SHARDS_REFUSE_ABOVE,
    }
