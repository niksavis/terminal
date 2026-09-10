r"""`fsck` and `rebuild` — the two commands that make "the log is the truth" checkable.

§13 in `SPEC.md` names them together and says why: without a check that
folds the whole log and reports what it finds, and a rebuild that regenerates every
derivative from the log alone, "the log is the truth" is a claim nobody can test. This
module is both, and it owns no state of its own — every defect it names is a property of
files `events.py` and `snapshot.py` already know how to read.

## Three severities, and the exit code is the difference between two remedies

A checker that says only *bad* leaves the reader to work out what to do, so the report
sorts its findings by what fixes them:

- :data:`BROKEN` — a defect in the **log**. `rebuild` cannot touch it: §4.4's rule is that
  fsck repairs only by appending corrective events and never by editing a line, or it
  quietly becomes an editor and the log stops being the truth. Exit :data:`EXIT_BROKEN`.
- :data:`DERIVED` — a snapshot or checkpoint that **disagrees with the log it claims to
  summarise**. `rebuild` fixes it by replacement. Exit :data:`EXIT_DERIVED`.
- :data:`WARNING` — an event kind **nothing** folds. Never a failure (§4.5): an old reader
  hitting a newer ledger must not report false corruption. A kind a sibling folds is a census
  line instead — it fired on 1,015 of 5,611 events until basicly-vkh0.38.

## Which derived state is worth checking, which is not, and why they differ

A stale derivative is **not** a finding. The snapshot is derived, gitignored and
disposable; `snapshot.load` scans the log and regenerates on a stale read, so a snapshot
that lags the log is the design working. An *absent* one is likewise nothing — anybody may
delete it.

The case that matters is the one the cheap check cannot reach. `snapshot.staleness`
compares a line count and a tip id, which is one-directional by construction: it may say
stale when the file is fresh, and never fresh when it is stale. What it cannot see is a
derivative whose header agrees with the log and whose **body** does not — a hand-edited
snapshot, a checkpoint written before an archive was appended to by a union merge, a half
file some other tool produced. `snapshot.load` serves that one verbatim, and `fold_resumed`
seeds the next snapshot from it. So this is the one place a fold is spent on a derived file,
and it is spent only where the header claims currency: for each derivative, the log files it
covers are folded and the whole file compared. Anything else is left to the lazy path.

## What the check may not assume, since it runs on the corrupt case by definition

`events.fold` **raises** on a known kind carrying a payload it cannot mean — a ``field``
with no name, a ``status`` with no status — which is right for a reader that must be correct
and fatal for a checker that dies on the corruption it exists to find. The whole fold is
therefore tried first and, only if it refuses, each event is folded alone to name the ones
responsible; the rest fold without them. That fallback costs one fold per event and is paid
exactly on ledgers that are already broken.

Two findings are then **suppressed rather than reported**, both for the same reason. §4.6
makes a forked item's carried totals void until a fold restates them, so a totals
disagreement on a forked record is the fork's consequence and not a second defect; the same
holds for a record whose fold is missing a malformed event. Reporting the consequence beside
the cause is how a report of eleven findings hides its one root cause.

## The derived set is a function of the log, which is what lets `rebuild` delete first

`snapshot.rebuild` regenerates the snapshot. This module's :func:`rebuild` regenerates
**every** derivative, which is §13's wording and a stronger claim: the set of derived files
is derived too. A checkpoint belongs to every closed period — every log file but the last —
because that is the invariant `snapshot.rotate` maintains, one checkpoint published per
boundary it closes. So the whole set is deleted (`snapshot.derived_paths`, whose contract is
that a log can never appear in it) and written again from the log, rather than repaired in
place. A derivative missing, corrupt or orphaned all end at the same place, and running it
twice changes nothing.

No lock is taken. A rotation moves where an append lands and needs one; this replaces caches
and cannot lose an event, and a concurrent append leaves the result stale rather than wrong —
the scan-before-fold order in :func:`derive` is what keeps that one-directional.

Standard library only, no `basicly` import, and every sibling loaded by path under the name
its own loaders use, so one `events` module object is shared across the kit.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --- the sibling modules ------------------------------------------------------

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:
    """Load a sibling kit module by path, without touching ``sys.path``.

    The cache lookup is the point rather than the speed: a second load mints a second
    ``Event`` class, and a frozen dataclass compares unequal across the two, so a snapshot
    read through one copy would never equal a fold taken through the other. Every loader in
    the kit uses these same module names for exactly that reason.

    Raises:
        ImportError: *file_name* is not beside this file. Deliberately not the ledger's own
            error family, which is defined in a module this may be loading.
    """
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
events = snapshot.events

# --- what an edge points at ---------------------------------------------------

# The kit writes edges in two dialects: `migrate.py` records `from`/`to`/`type` and
# `differential.py` reads that spelling, while `provenance.py` declares `target`/`edge_type`
# as the one spelling and cites the defect two spellings caused (basicly-kjc5.10). Reconciling
# them is not this module's to do, and knowing only one of them is not an option either: a
# checker blind to a dialect passes the log it exists to fail. Both are read from the modules
# that declare them, so neither is spelled a third time here.
EDGE_KINDS = frozenset({migrate.KIND_EDGE, provenance.KIND_EDGE})
EDGE_RECORD_KEYS = tuple(sorted({migrate.EDGE_FROM, migrate.EDGE_TO, provenance.KEY_TARGET}))

# --- severities and exit codes ------------------------------------------------

# A defect in the log. `rebuild` cannot repair one; only a corrective event can (§4.4).
BROKEN = "broken"
# A derived file that disagrees with the log. `rebuild` replaces it.
DERIVED = "derived"
# Reported and never fatal — forward compatibility (§4.5).
WARNING = "warning"

EXIT_CLEAN = 0
EXIT_DERIVED = 1
EXIT_BROKEN = 2

# --- the finding classes ------------------------------------------------------

# A newline-terminated line the parser refused. The torn *trailing* line `events.read_log`
# tolerates never reaches here; interior garbage always does (§4.4).
UNPARSEABLE = "unparseable"
# An event of a kind the fold knows, carrying a payload that kind cannot mean. The fold
# refuses it, so no later fold of this ledger can succeed either.
MALFORMED = "malformed"
# Two distinct events claiming one item's sequence number — §4.1's visible fork.
FORKED_SEQUENCE = "forked-sequence"
# A sequence number **no** event claims, below the item's highest — the fork's other half, and
# unreported until basicly-t10ipy, where this ledger's only symptom was the CARRIED_TOTALS
# consequence on every later event. :func:`_gap_findings` states what a hole means.
SEQUENCE_GAP = "sequence-gap"
# One content-derived id on lines that disagree about their content, so the id no longer
# identifies what it names and the fold's dedup silently picks one.
DUPLICATE_ID = "duplicate-id"
# An event about a record no `created` event ever minted.
DANGLING_RECORD = "dangling-record"
# An edge whose target was never created — an edge into nothing (§13, referentially broken).
DANGLING_EDGE = "dangling-edge"
# An event whose carried totals disagree with the fold. The fold is the authority; this is a
# finding and never a repair in place (§4.6).
CARRIED_TOTALS = "carried-totals"
# A derived file that exists and cannot be read as one.
DERIVED_UNREADABLE = "derived-unreadable"
# A derived file whose header claims to be current and whose body is not what the log folds to.
DERIVED_DISAGREES = "derived-disagrees"
# A kind no module folds: a newer writer's, or a malformed one. A warning and not a failure,
# because neither is corruption — but a finding, which a delegated kind is not.
UNFOLDED_KIND = "unfolded-kind"
# An event whose id does not re-mint from the record, kind and payload on its own line, so
# the line was rewritten in place by something that is not `events.withdraw` (basicly-vkh0.34).
# The one check that makes "only the withdrawal path rewrites the log" a fact about the file
# rather than a promise: an id digests the payload, so an edit that leaves the id alone breaks
# the derivation. It catches an edit, not a forger — a rewrite that re-minted the id too reads
# as an ordinary append, and nothing in a single file can tell those apart.
UNMINTED_ID = "unminted-id"
# A payload carrying a withdrawal marker that no `withdrawn` event names, and its mirror: a
# `withdrawn` event whose target is not in the log. One withdrawal is two writes — the rewrite
# and the trail — so either alone is the half that did not land.
WITHDRAWAL_UNRECORDED = "withdrawal-unrecorded"
WITHDRAWAL_UNAPPLIED = "withdrawal-unapplied"
# The retired line is back: a withdrawal rewrote a line, and a union merge of a branch holding
# the old bytes re-added it. Both lines now parse and fold, so this is the only signal that the
# withdrawn content is readable again.
WITHDRAWAL_RESURRECTED = "withdrawal-resurrected"
# A label write naming a label of one character; `label_shape.py` holds why that is the
# signature of a string iterated rather than split. :data:`BROKEN` on that constant's own
# terms — the log is internally consistent, so only a corrective write can clear it.
SPLIT_LABEL = "split-label"

# How many carrying event ids one finding prints. Measured rather than guessed: the first run
# against this repo's own 642-record ledger printed a clean report as 656 ids under a single
# warning, which is a wall a reader scrolls past rather than a report. Attribute:`Finding.event_ids`
# still holds every one for a programmatic caller; only the printed form is bounded, and it
# **says how many it dropped** — a silent cap reads as "that was all of them".
MAX_EVENT_IDS_REPORTED = 10


@dataclass(frozen=True)
class Finding:
    """One thing wrong with the ledger, named by what carries it.

    Attributes:
        kind: The finding class — one of the module constants above.
        severity: :data:`BROKEN`, :data:`DERIVED` or :data:`WARNING`.
        subject: What the finding is about: a record id, an event id, a kind, or a
            ``name:line`` position. A file **name**, never a path, so a report is portable.
        detail: Why it is a finding, in a sentence a reader can act on.
        event_ids: Every event id carrying it, in sorted order — all of them, however many.
            Empty only where there is no event to name; an unparseable line has no id, which
            is why it is unparseable.
    """

    kind: str
    severity: str
    subject: str
    detail: str
    event_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """The JSON form printed in the report, with the id list bounded and the cut declared."""
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
    """What one `fsck` run found.

    Attributes:
        directory: The ledger checked.
        findings: Every finding, grouped by class and sorted within it, so two runs over one
            ledger print identically.
        events: Events the fold consumed, malformed ones excluded.
        records: Records in the fold.
        delegated_kinds: ``(kind, count, the sibling fold that owns it)`` per kind the record
            fold leaves to a sibling. A census, not a finding, so the population reads as
            counted rather than as gone.
        unattributed: Events naming no actor, over the same set as :attr:`events`. A census on
            `delegated_kinds`' grounds, and because no event can supply a missing actor.
    """

    directory: Path
    findings: tuple[Finding, ...] = ()
    events: int = 0
    records: int = 0
    delegated_kinds: tuple[tuple[str, int, str], ...] = ()
    unattributed: int = 0

    def of_severity(self, severity: str) -> tuple[Finding, ...]:
        """Every finding at *severity*."""
        return tuple(found for found in self.findings if found.severity == severity)

    @property
    def clean(self) -> bool:
        """True when nothing but warnings was found."""
        return not self.of_severity(BROKEN) and not self.of_severity(DERIVED)

    @property
    def exit_code(self) -> int:
        """The process exit status: broken beats derived beats clean."""
        if self.of_severity(BROKEN):
            return EXIT_BROKEN
        if self.of_severity(DERIVED):
            return EXIT_DERIVED
        return EXIT_CLEAN

    def as_dict(self) -> dict[str, object]:
        """The JSON form the entry point prints."""
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


# --- deriving a file from a set of logs ---------------------------------------


def derive(paths: Sequence[Path]) -> Any:
    """The ``snapshot.Snapshot`` that folding *paths* — and nothing else — produces.

    One function for both callers, which is what makes the check falsifiable: :func:`check`
    compares a derived file against this and :func:`rebuild` writes it, so a derivative
    passes exactly when it is what a rebuild would have written.

    **The scan runs before the fold**, per `snapshot.py`'s invariant. A header taken after
    the fold could claim to have folded a line it never saw and so read as *fresh* while
    being stale, and that is the one error the design cannot absorb.

    Args:
        paths: The log files this derivative covers — every log for the snapshot, the ones
            up to its boundary for a checkpoint.

    Raises:
        events.InvalidEventError: an event of a known kind carries a payload that kind
            cannot mean. Refused rather than folded around: a derivative built by skipping
            an event the reader could not understand is a wrong answer with a fresh header.
    """
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
    """The log files a checkpoint at *boundary* covers: every period up to and including it.

    `snapshot.logs_after`'s complement, and the set `snapshot.fold_resumed` scans when it
    decides whether a checkpoint may still be trusted — so a checkpoint this module rebuilds is
    one that function accepts.
    """
    return [path for path in events.log_paths(directory) if snapshot.period_of(path) <= boundary]


def derived_targets(directory: Path | str) -> list[tuple[Path, list[Path]]]:
    """Every derivative the log implies, with the log files each one covers.

    Derived from the **log**, not from what is on disk: the snapshot, plus one checkpoint per
    closed period — every log file but the last, which is `snapshot.rotate`'s invariant, one
    checkpoint published per boundary it closes. That is what lets :func:`rebuild` restore a
    derivative somebody deleted rather than only replacing the ones that survived.
    """
    ledger = Path(directory)
    logs = events.log_paths(ledger)
    targets: list[tuple[Path, list[Path]]] = []
    for closed in logs[:-1]:
        boundary = snapshot.period_of(closed)
        targets.append((snapshot.checkpoint_path(ledger, boundary), covered_logs(ledger, boundary)))
    targets.append((snapshot.snapshot_path(ledger), logs))
    return targets


# --- the check ----------------------------------------------------------------


def _malformed(collected: Sequence[Any]) -> list[tuple[int, Any, str]]:
    """``(position, event, reason)`` for each event the fold refuses on its own.

    Folding one event at a time rather than re-deciding what each kind requires: the rule
    lives in `events.py`'s handlers, and a second copy of it here would drift from the fold
    it is meant to describe. Positions rather than identities, because two equal events are
    equal dataclasses and a set would collapse them.
    """
    refused: list[tuple[int, Any, str]] = []
    for position, event in enumerate(collected):
        try:
            events.fold([event])
        except events.InvalidEventError as exc:
            refused.append((position, event, str(exc)))
    return refused


def _unparseable_findings(quarantined: Iterable[Any]) -> list[Finding]:
    """One finding per quarantined line, named by position because it has no id."""
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
    """One finding per event the fold refuses."""
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
    """One finding per item sequence number two distinct events both claim.

    `events.FoldResult.forked` reports the same condition at record granularity; this narrows
    it to the events, which is what a reader needs to append the corrective one.
    """
    claimed: dict[tuple[str, int], list[str]] = {}
    for event in ordered:
        claimed.setdefault((event.record, event.seq), []).append(event.id)
    return [
        Finding(
            kind=FORKED_SEQUENCE,
            severity=BROKEN,
            subject=record,
            detail=(
                f"{len(found)} events claim sequence {seq} on this record, so their order is a "
                f"tie broken by id rather than a decision, and its carried totals are void "
                f"until a fold restates them"
            ),
            event_ids=tuple(sorted(found)),
        )
        for (record, seq), found in sorted(claimed.items())
        if len(found) > 1
    ]


def sequence_gaps(ordered: Sequence[Any]) -> dict[str, tuple[int, ...]]:
    """Record to the sequence numbers below its highest that no event claims.

    Separate from :func:`_gap_findings` because the answer is needed twice: once to report the
    gap, and once to void the carried totals of every event after it. A record is missing an
    event, so every total downstream of the hole is off by the same amount — reporting each of
    those beside the hole is the eleven-findings shape §4.6 already avoids for a fork.
    """
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
    """One finding per record whose sequence chain has a hole in it.

    No ``event_ids``: the defect is precisely that the events are *not* here, and naming the
    survivors either side would point a reader at two sound lines. The missing numbers are the
    evidence, and nothing can restore what they named — an append-only log has no undelete, so
    this is reported to be *known* rather than to be repaired.
    """
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
    """One finding per id whose lines disagree about what that id names.

    A repeated id is **ordinary**: a union merge duplicates a hunk and the fold keeps one,
    which is what content-derived ids are for. It is a defect only when the lines differ,
    because the id covers the record, the kind and the payload — so a disagreement there means
    the digest no longer matches its content — or when they differ in sequence number, which
    the id does not cover and the dedup silently decides. ``ts`` and ``actor`` may differ
    freely: excluding them from the digest is what makes one fact minted on two branches under
    two clocks carry one id (§9.4, §9.5).
    """
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
    """Findings for records spoken about but never created, and edges into nothing.

    A record exists once a ``created`` event mints it, and a tombstoned record still exists —
    a delete leaves a tombstone rather than removing anything, so an edge into one is a
    reference to a record that says it is gone, which is not the same as a reference to
    nothing. Grouped by the **missing** record so its every referent is named once.
    """
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
    """Findings for carried totals the fold disagrees with, minus the ones already explained.

    §4.6 makes a forked item's carried totals **void until a fold restates them**, so on a
    forked record the disagreement is the fork's consequence rather than a second defect; a
    record whose fold is missing a malformed event is void for the same reason. Reporting a
    consequence beside its cause is how one root defect prints as eleven findings.
    """
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
    """One warning per kind **no** module folds, never a failure (§4.5).

    A delegated kind is absent on purpose: counting it here is what made the old text offer
    two readings, neither actionable.
    """
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
    """Whether *event*'s id is the one its own content mints, at any generation up to *bound*.

    Any generation rather than the dense occurrence count, and the bound is what keeps that
    honest: a withdrawal changes a payload, so its event leaves the group of identical
    payloads it was counted in and the survivors' generations stop being dense. Requiring
    density would report those survivors as edited, which is a false report of the defect
    this check exists to find. *bound* is the record's own event count, since no generation
    can exceed the number of times its record was written to.
    """
    for generation in range(1, bound + 1):
        if event.id == events.event_id_for(
            event.record, event.kind, event.payload, generation=generation
        ):
            return True
    return False


def _unminted_id_findings(ordered: Sequence[Any]) -> list[Finding]:
    """One finding per event whose line disagrees with the id on it.

    A record id that is not one is skipped rather than reported: `event_id_for` refuses it,
    and :func:`_reference_findings` already names the record that was never created.
    """
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
    """Findings for the one rewrite this log permits: a half-landed one, or an undone one.

    Three populations, all read off the log alone — the withdrawn lines, the trails that
    name them, and the ids those lines retired. A withdrawal is sound when the first two
    pair up exactly and the third names nothing the log still holds.
    """
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
    """One finding per record whose label writes name a one-character label.

    Over the events and not the fold, for `label_shape.labels_written_by`'s reason.
    """
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
    """Each delegated kind, its count, and the sibling fold `events.py` names for it.

    On :data:`EDGE_KINDS`' grounds: a seam spelled twice reports the checker's own copy.
    """
    return tuple(
        (kind, count, events.DELEGATED_KINDS[kind])
        for kind, count in sorted(folded.delegated_kinds.items())
    )


def _disagreement(present: Any, expected: Any) -> str:
    """How a derived file differs from what the log folds to, in one sentence."""
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
    """Findings for derived files that claim to be current and are not.

    Absent is nothing and stale is nothing: both are the lazy regeneration `snapshot.load`
    already performs, and a derivative anybody may delete cannot be a defect for being
    deleted. What is checked is the case no scan can reach — a header that agrees with the
    log over a body that does not, which `snapshot.load` serves verbatim and
    `snapshot.fold_resumed` seeds the next snapshot from.
    """
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


def check(directory: Path | str) -> Report:
    """Fold the whole log, compare every derivative against it, and report what disagrees.

    The full-history fold, never the resumed one: it is the only fold that can see a fork
    straddling a rotation boundary, and the only one whose answer does not rest on a derived
    file being right.

    A ledger directory that does not exist reports clean rather than raising. A checker wired
    into a repository that has no tracker must be inert, not an error.

    Args:
        directory: The ledger directory holding the log files.

    Returns:
        The report. Its :attr:`Report.exit_code` says which remedy applies.
    """
    ledger = Path(directory)
    found, quarantined = events.read_events(ledger)
    malformed: list[tuple[int, Any, str]] = []
    try:
        folded = events.fold(found)
        sound = list(found)
    except events.InvalidEventError:
        # Only now is the per-event fold worth its cost, and only a ledger already broken
        # ever pays it. The events that survive fold together: each handler reads its own
        # event's payload, so a set of individually sound events cannot refuse as a batch.
        malformed = _malformed(found)
        refused = {position for position, _, _ in malformed}
        sound = [event for position, event in enumerate(found) if position not in refused]
        folded = events.fold(sound)
    ordered = events.canonical_order(sound)
    gaps = sequence_gaps(ordered)
    # A hole in the chain voids the same cache a fork does, and for the same reason: the fold
    # counts the events that are here and the carried totals counted one that is not, so the
    # disagreement downstream of the hole is its consequence rather than a second defect.
    voided = set(folded.forked) | {event.record for _, event, _ in malformed} | set(gaps)

    # One population, two spellings: the empty field, and the reason that replaced it.
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
    if not malformed:
        # Every derivative is a fold of the log, so a log the fold refuses has no derivative
        # to be right or wrong against. Saying so beats reporting a cache for its source.
        findings += _derived_findings(ledger)
    return Report(
        directory=ledger,
        findings=tuple(findings),
        events=len(ordered),
        records=len(folded.records),
        delegated_kinds=_delegated_census(folded),
        unattributed=unattributed,
    )


# --- the rebuild --------------------------------------------------------------


@dataclass(frozen=True)
class Rebuild:
    """What one `rebuild` replaced.

    Attributes:
        directory: The ledger rebuilt.
        removed: The derived files deleted first, in `snapshot.derived_paths` order.
        written: The derived files written, checkpoints in period order then the snapshot.
    """

    directory: Path
    removed: tuple[Path, ...] = ()
    written: tuple[Path, ...] = ()


def rebuild(directory: Path | str) -> Rebuild:
    """Delete every derived file and write the set the log implies, from the log alone.

    §13's recovery for a corrupt derivative is *delete and rebuild, never repair in place*,
    and this is that sentence: `snapshot.derived_paths` is the deletable set — a contract that
    a log can never appear in it — and :func:`derived_targets` is what the log says should be
    there. A derivative that is corrupt, stale, missing or left over from a period the log no
    longer has all end in the same state, and a second run changes nothing.

    Nothing derived seeds the repair, including the files being replaced: a rebuild that
    resumed from a checkpoint would be reading the thing under repair. A replaced file's
    record count is read, and only that — it decides the refusal below, never a fold.

    Args:
        directory: The ledger directory. Left alone entirely when it does not exist.

    Returns:
        What was removed and what was written.

    Raises:
        events.InvalidEventError: from :func:`derive` — the log holds an event of a known
            kind that the fold refuses, so there is no correct derivative to write. `check`
            names the events; only a corrective event fixes it.
        snapshot.SnapshotError: a derivative would hold fewer records than the file it
            replaces. Both counts are in the message; nothing is removed and nothing written.
    """
    ledger = Path(directory)
    if not ledger.is_dir():
        return Rebuild(directory=ledger)
    # Derived and compared before anything is deleted (basicly-dx2ngn). `write_snapshot`'s
    # shrink guard compares against the file on disk and the unlink below guarantees there is
    # none, so R9's refusal could never fire through this path. Taking it after the unlink
    # would destroy the records it exists to keep, so a refused rebuild removes nothing.
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


# --- the entry point ----------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """Check one ledger, or rebuild its derivatives and check what that produced.

    ``--rebuild`` runs the check afterwards on purpose: a repair nobody verified is a claim,
    and the exit code is the check's either way — so a clean run after a rebuild is evidence
    that the derived files now match the log rather than that a write did not raise.

    Returns:
        :data:`EXIT_CLEAN` when nothing but warnings was found, :data:`EXIT_DERIVED` when a
        derivative disagrees with the log and a rebuild would fix it, :data:`EXIT_BROKEN`
        when the log itself is defective and only a corrective event can.
    """
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
    """The printed report. Indented because a person reads it, sorted so two runs match."""
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False)


def _dumps(obj: Mapping[str, object]) -> str:
    """One payload rendered canonically, so two lines are compared by content and not by order."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
