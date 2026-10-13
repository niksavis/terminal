from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    key = "basicly_tracker_kit_" + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, _HERE / (name + ".py"))
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's " + name + ".py is missing from beside it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


events = _load("events")
shaping = _load("shaping")
labels = _load("labels")
evidence_checks = _load("evidence_checks")
_text = evidence_checks.filled_text
_command = evidence_checks.filled_command
_check_fault = evidence_checks.check_fault
criterion_key = evidence_checks.criterion_key
criteria = evidence_checks.criteria
check_shape = evidence_checks.check_shape
REVIEW_FIELD = "process_review"
CONFIRMATION_FIELD = "process_confirmation"
RESOLUTION_FIELD = "close_resolution"
VERSION_FIELD = "process_evidence_version"
VERSION = 1
INVEST = ("independent", "negotiable", "valuable", "estimable", "small", "testable")
INVEST_HEADING = "## INVEST Review"
CONVERSATION_HEADING = "## Conversation"
PLAN_HEADING = "## Confirmation Plan"
COMPLETION_HEADING = "## Completion Confirmation"
SEMANTIC_FIELDS = frozenset({
    "title",
    "description",
    "acceptance_criteria",
    "requirements",
    "issue_type",
})
MANAGED_FIELDS = frozenset({REVIEW_FIELD, CONFIRMATION_FIELD})


class ProcessEvidenceError(events.LedgerError):
    pass


def _semantic(event: Any, record: str, names=SEMANTIC_FIELDS) -> bool:
    return event.record == record and (
        event.kind == events.KIND_CREATED
        or (event.kind == events.KIND_FIELD and event.payload.get("name") in names)
        or event.kind in (events.KIND_EDGE, events.KIND_EDGE_RETRACTED)
    )


def revision(
    found: Sequence[Any],
    record: str,
    fields: Mapping[str, object] | None = None,
    drafts: Sequence[Any] = (),
    *,
    template=None,
) -> str:
    states = events.fields_by_record(found)
    held = dict(fields) if fields is not None else dict(states[record])
    headings = shaping.required(held, template)
    names = SEMANTIC_FIELDS | frozenset(shaping.field_of(heading) for heading in headings)
    semantic = sorted({event.id for event in found if _semantic(event, record, names)})
    pending = [dict(draft.payload) for draft in drafts if _semantic(draft, record, names)]
    content = {name: held.get(name) for name in sorted(names)}
    edges = {}
    for event in events.canonical_order(found):
        if event.record == record and event.kind in (events.KIND_EDGE, events.KIND_EDGE_RETRACTED):
            target_key, type_key = labels.DIALECT_KEYS[labels.edge_dialect(event.payload)]
            edges[(event.payload.get(target_key), event.payload.get(type_key))] = (
                event.kind == events.KIND_EDGE
            )
    targets = sorted({
        target for (target, _kind), active in edges.items() if active and isinstance(target, str)
    })
    dependencies = {}
    for target in targets:
        fields = states.get(target, {})
        target_headings = shaping.required(fields, template)
        target_names = SEMANTIC_FIELDS | frozenset(
            shaping.field_of(heading) for heading in target_headings
        )
        dependencies[target] = [
            target_headings,
            sorted({event.id for event in found if _semantic(event, target, target_names)}),
        ]
    packed = json.dumps(
        [record, semantic, content, pending, dependencies, headings],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def _saved(found: Sequence[Any], record: str, fields: Mapping[str, object], name: str) -> Mapping:
    raw = fields.get(name)
    if not isinstance(raw, str):
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(value, Mapping):
        return {}
    matching = [
        event
        for event in found
        if event.record == record
        and event.kind == events.KIND_FIELD
        and event.payload.get("name") == name
    ]
    if not matching:
        return {}
    last = events.canonical_order(matching)[-1]
    return (
        value
        if last.payload.get("value") == raw
        and last.payload.get(VERSION_FIELD) == VERSION
        and value.get("writer") == last.actor
        else {}
    )


def _conversation(found: Sequence[Any], record: str, references: object) -> bool:
    if not isinstance(references, list) or not references:
        return False
    for reference in references:
        if not isinstance(reference, int) or isinstance(reference, bool) or reference <= 0:
            return False
        matching = [
            event
            for event in events.canonical_order(found)
            if event.record == record and event.seq == reference
        ]
        if (
            len(matching) != 1
            or matching[0].kind not in events.PROSE_KINDS
            or not _text(matching[0].payload.get("text"))
        ):
            return False
    return len(set(references)) == len(references)


def _checks(fields: Mapping[str, object], checks: object, *, completed: bool = False) -> bool:
    return _check_fault(fields, checks, completed=completed) is None


def review_note(
    found: Sequence[Any],
    record: str,
    fields: Mapping[str, object],
    drafts: Sequence[Any] = (),
    *,
    template=None,
) -> str:
    saved = _saved(found, record, fields, REVIEW_FIELD)
    if not saved:
        return "no review is recorded; run review --evidence"
    if saved.get("revision") != revision(found, record, fields, drafts, template=template):
        return "the recorded review is void because the record changed after it; run review again"
    return ""


def readiness(
    found: Sequence[Any],
    record: str,
    fields: Mapping[str, object] | None = None,
    drafts: Sequence[Any] = (),
    *,
    template=None,
) -> tuple[str, ...]:
    if fields is None:
        state = events.fold(found).records.get(record)
        held = dict(state.fields) if state is not None else {}
    else:
        held = dict(fields)
    saved = _saved(found, record, held, REVIEW_FIELD)
    current = bool(saved) and saved.get("revision") == revision(
        found, record, held, drafts, template=template
    )
    rationales = saved.get("invest") if current else {}
    rationales = rationales if isinstance(rationales, Mapping) else {}
    missing = [
        f"{INVEST_HEADING}: {quality}" for quality in INVEST if not _text(rationales.get(quality))
    ]
    if not current or not _conversation(found, record, saved.get("conversation")):
        missing.append(CONVERSATION_HEADING)
    if not current or not _checks(held, saved.get("checks")):
        missing.append(PLAN_HEADING)
    return tuple(missing)


def _draft(record: str, name: str, value: Mapping[str, object], writer: str) -> Any:
    return events.Draft(
        record,
        events.KIND_FIELD,
        {
            "name": name,
            "value": json.dumps({**value, "writer": writer}, sort_keys=True),
            VERSION_FIELD: VERSION,
        },
    )


def _machine_path(checks: Sequence[Mapping[str, Any]]) -> str | None:

    rules = _load("beads").MACHINE_PATH_RULES
    for check in checks:
        if any(pattern.search(part) for part in check["command"] for _, pattern in rules):
            return str(check["criterion"])
    return None


def review_draft(
    found: Sequence[Any], record: str, payload: object, writer: str, *, template=None
) -> Any:
    state = events.fold(found).records.get(record)
    if state is None or state.tombstoned:
        raise ProcessEvidenceError("the ledger holds no record " + record)
    if not isinstance(payload, dict) or set(payload) != {"invest", "conversation", "checks"}:
        raise ProcessEvidenceError(
            "review requires invest, conversation and checks; revision and writer are computed"
        )
    rationales = payload["invest"]
    if (
        not isinstance(rationales, dict)
        or set(rationales) != set(INVEST)
        or not all(_text(rationales.get(quality)) for quality in INVEST)
    ):
        raise ProcessEvidenceError(
            "INVEST review requires a filled rationale for " + ", ".join(INVEST)
        )
    if not _conversation(found, record, payload["conversation"]):
        raise ProcessEvidenceError(
            "Conversation requires same-card comment seqs without forks; read show comment_log"
        )
    if fault := _check_fault(state.fields, payload["checks"]):
        raise ProcessEvidenceError(f"Confirmation Plan refused: {fault}")
    if (criterion := _machine_path(payload["checks"])) is not None:
        raise ProcessEvidenceError(
            f"Confirmation Plan command for {criterion!r} holds a machine path that the ledger "
            "redacts, which would void the review; name the program on PATH, such as python3 "
            "or uv run, or a path relative to the repository"
        )
    value = {**payload, "revision": revision(found, record, template=template)}
    return _draft(record, REVIEW_FIELD, value, writer)


def confirmation_report(found: Sequence[Any], record: str, *, template=None) -> dict[str, Any]:
    state = events.fold(found).records.get(record)
    fields = dict(state.fields) if state is not None else {}
    return {
        "revision": revision(found, record, fields, template=template),
        "owed": list(readiness(found, record, fields, template=template)),
        "review": dict(_saved(found, record, fields, REVIEW_FIELD)),
        "confirmation": dict(_saved(found, record, fields, CONFIRMATION_FIELD)),
    }


def confirmation_draft(
    found: Sequence[Any], record: str, payload: object, writer: str, *, template=None
) -> Any:
    report = confirmation_report(found, record, template=template)
    if report["owed"]:
        raise ProcessEvidenceError(
            "confirm requires a current review: " + ", ".join(str(part) for part in report["owed"])
        )
    state = events.fold(found).records[record]
    if not isinstance(payload, dict) or set(payload) != {"checks"}:
        raise ProcessEvidenceError(
            "Completion Confirmation refused: evidence holds the one key checks; "
            + check_shape(completed=True)
        )
    if fault := _check_fault(state.fields, payload["checks"], completed=True):
        raise ProcessEvidenceError(f"Completion Confirmation refused: {fault}")
    review = report["review"]
    if not isinstance(review, Mapping):
        raise ProcessEvidenceError("confirm requires a recorded review")
    planned = {criterion_key(check["criterion"]): check["command"] for check in review["checks"]}
    if any(
        planned[criterion_key(check["criterion"])] != check["command"]
        for check in payload["checks"]
    ):
        raise ProcessEvidenceError(
            "Completion Confirmation command argv must match the agreed plan for that criterion"
        )
    return _draft(record, CONFIRMATION_FIELD, {**payload, "revision": report["revision"]}, writer)


def closing_owed(
    found: Sequence[Any],
    record: str,
    fields: Mapping[str, object],
    drafts: Sequence[Any] = (),
    *,
    template=None,
) -> tuple[str, ...]:
    missing = readiness(found, record, fields, drafts, template=template)
    saved = _saved(found, record, fields, CONFIRMATION_FIELD)
    complete = saved.get("revision") == revision(
        found, record, fields, drafts, template=template
    ) and _checks(fields, saved.get("checks"), completed=True)
    review = _saved(found, record, fields, REVIEW_FIELD)
    planned = {
        criterion_key(check["criterion"]): check["command"]
        for check in review.get("checks", [])
        if isinstance(check, dict) and "criterion" in check and "command" in check
    }
    complete = complete and all(
        planned.get(criterion_key(check["criterion"])) == check["command"]
        for check in saved.get("checks", [])
    )
    return (*missing, *((COMPLETION_HEADING,) if not complete else ()))


def record_process(
    directory: Path | str,
    record: str,
    evidence: object,
    *,
    completed: bool = False,
    redact: Callable[[str], str] | None = None,
) -> list:
    commands = _load("commands")
    ledger = commands._ledger(directory)
    with events.LedgerLock(ledger) as lock:
        commands._require(ledger, record)
        found = events.read_events(ledger)[0]
        builder = confirmation_draft if completed else review_draft
        draft = builder(
            found,
            record,
            evidence,
            commands.writers.writer_class(),
            template=commands.templates.load(ledger),
        )
        return commands._append(ledger, [draft], redact, lock)
