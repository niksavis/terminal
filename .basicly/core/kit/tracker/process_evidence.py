from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
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
small_task = _load("small_task")
conversation = _load("conversation")
small = small_task.small
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
NO_REVIEW = "no review is recorded; run review --evidence"


class ProcessEvidenceError(evidence_checks.NextStepsError, events.LedgerError):
    pass


def _semantic(event: Any, record: str, names=SEMANTIC_FIELDS) -> bool:
    return event.record == record and (
        event.kind == events.KIND_CREATED
        or (event.kind == events.KIND_FIELD and event.payload.get("name") in names)
        or event.kind in (events.KIND_EDGE, events.KIND_EDGE_RETRACTED)
    )


def _headings(fields: Mapping[str, object], template, legacy: bool) -> tuple:
    if not legacy:
        return shaping.required(fields, template)
    base = (shaping.TRIGGER_HEADING, shaping.ACCEPTANCE_HEADING, shaping.REQUIREMENTS_HEADING)
    if template is None:
        return base
    kind = fields.get(shaping.TYPE_FIELD)
    extra = template.for_type(kind if isinstance(kind, str) else "")
    return tuple(dict.fromkeys((*(base if template.extends else ()), *template.sections, *extra)))


@dataclass(frozen=True)
class RevisionContext:
    fields: Mapping[str, object] | None = None
    drafts: Sequence[Any] = ()
    template: Any = None
    legacy: bool = False
    index: Any = None


def revision(
    found: Sequence[Any],
    record: str,
    fields: Mapping[str, object] | None = None,
    drafts: Sequence[Any] = (),
    *,
    template=None,
) -> str:
    return _revision(found, record, RevisionContext(fields, drafts, template))


def _revision(found: Sequence[Any], record: str, context: RevisionContext) -> str:
    fields, drafts, template, legacy = (
        context.fields,
        context.drafts,
        context.template,
        context.legacy,
    )
    states, grouped = context.index if context.index is not None else events.record_index(found)
    held = dict(fields) if fields is not None else dict(states[record])
    headings = _headings(held, template, legacy)
    names = SEMANTIC_FIELDS | frozenset(shaping.field_of(heading) for heading in headings)
    own = grouped.get(record, ())
    semantic = sorted({event.id for event in own if _semantic(event, record, names)})
    pending = [dict(draft.payload) for draft in drafts if _semantic(draft, record, names)]
    content = {name: held.get(name) for name in sorted(names)}
    edges = {}
    for event in own:
        if event.kind in (events.KIND_EDGE, events.KIND_EDGE_RETRACTED):
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
        target_headings = _headings(fields, template, legacy)
        target_names = SEMANTIC_FIELDS | frozenset(
            shaping.field_of(heading) for heading in target_headings
        )
        dependencies[target] = [
            target_headings,
            sorted({
                event.id
                for event in grouped.get(target, ())
                if _semantic(event, target, target_names)
            }),
        ]
    packed = json.dumps(
        [record, semantic, content, pending, dependencies, headings],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def _current(saved, found, record, context: RevisionContext) -> bool:
    if not saved:
        return False
    value = saved.get("revision")
    order = (False, True) if saved.get("contract") == shaping.SHAPING_RULE else (True, False)
    return any(
        value == _revision(found, record, replace(context, legacy=legacy)) for legacy in order
    )


def _saved(
    found: Sequence[Any], record: str, fields: Mapping[str, object], name: str, index: Any = None
) -> Mapping:
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
        for event in (index if index is not None else events.record_index(found))[1].get(record, ())
        if event.kind == events.KIND_FIELD and event.payload.get("name") == name
    ]
    if not matching:
        return {}
    last = matching[-1]
    return (
        value
        if last.payload.get("value") == raw
        and last.payload.get(VERSION_FIELD) == VERSION
        and value.get("writer") == last.actor
        else {}
    )


def _checks(fields: Mapping[str, object], checks: object, *, completed: bool = False) -> bool:
    return _check_fault(fields, checks, completed=completed) is None


def _compact_type(fields: Mapping[str, object]) -> bool:
    return fields.get("issue_type") in ("task", "bug", "chore")


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
        return NO_REVIEW
    if not _current(saved, found, record, RevisionContext(fields, drafts, template)):
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
    return _readiness(found, record, RevisionContext(fields, drafts, template))


def readiness_many(
    found: Sequence[Any], fields: Mapping[str, Mapping[str, object]], *, template: Any = None
) -> dict[str, tuple[str, ...]]:
    index = events.record_index(found)
    return {
        record: _readiness(found, record, RevisionContext(held, template=template, index=index))
        for record, held in fields.items()
    }


def _readiness(found: Sequence[Any], record: str, context: RevisionContext) -> tuple[str, ...]:
    fields = context.fields
    if fields is None:
        state = events.fold(found).records.get(record)
        held = dict(state.fields) if state is not None else {}
    else:
        held = dict(fields)
    if small(held):
        return small_task.owed(held, len(criteria(held)))
    saved = _saved(found, record, held, REVIEW_FIELD, context.index)
    current = _current(saved, found, record, replace(context, fields=held))
    if _compact_type(held) and (
        not current or set(saved) - {"contract"} == {"checks", "revision", "writer"}
    ):
        return () if current and _checks(held, saved.get("checks")) else (PLAN_HEADING,)
    rationales = saved.get("invest") if current else {}
    rationales = rationales if isinstance(rationales, Mapping) else {}
    missing = [
        f"{INVEST_HEADING}: {quality}" for quality in INVEST if not _text(rationales.get(quality))
    ]
    if not current or conversation.fault(found, record, saved.get("conversation")):
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


def _safe_commands(
    checks: Sequence[Mapping[str, Any]], redactor: Callable[[str], str] | None = None
) -> None:
    if fault := evidence_checks.command_privacy_fault(checks, redactor):
        raise ProcessEvidenceError(fault)


def review_draft(
    found: Sequence[Any], record: str, payload: object, writer: str, *, template=None
) -> Any:
    state = events.fold(found).records.get(record)
    if state is None or state.tombstoned:
        raise ProcessEvidenceError("the ledger holds no record " + record)
    if not isinstance(payload, dict):
        raise ProcessEvidenceError("review requires a JSON object")
    compact = _compact_type(state.fields) and set(payload) == {"checks"}
    if not compact and set(payload) != {"invest", "conversation", "checks"}:
        raise ProcessEvidenceError(
            "review requires invest, conversation and checks; task, bug and chore may use "
            "checks only; revision and writer are computed"
        )
    if not compact:
        _full_review(found, record, payload)
    if fault := _check_fault(state.fields, payload["checks"]):
        raise ProcessEvidenceError(f"Confirmation Plan refused: {fault}")
    _safe_commands(payload["checks"])
    value = {
        **payload,
        "revision": revision(found, record, template=template),
        "contract": shaping.SHAPING_RULE,
    }
    return _draft(record, REVIEW_FIELD, value, writer)


def _full_review(found: Sequence[Any], record: str, payload: Mapping[str, Any]) -> None:
    rationales = payload["invest"]
    if (
        not isinstance(rationales, dict)
        or set(rationales) != set(INVEST)
        or not all(_text(rationales.get(quality)) for quality in INVEST)
    ):
        raise ProcessEvidenceError(
            "INVEST review requires a filled rationale for " + ", ".join(INVEST)
        )
    if fault := conversation.fault(found, record, payload["conversation"]):
        raise ProcessEvidenceError(f"Conversation refused: {fault}; read show comment_log")


def confirmation_report(found: Sequence[Any], record: str, *, template=None) -> dict[str, Any]:
    state = events.fold(found).records.get(record)
    fields = dict(state.fields) if state is not None else {}
    return {
        "revision": revision(found, record, fields, template=template),
        "owed": list(readiness(found, record, fields, template=template)),
        "review_current": _current(
            _saved(found, record, fields, REVIEW_FIELD),
            found,
            record,
            RevisionContext(fields, template=template),
        ),
        "confirmation_current": _current(
            _saved(found, record, fields, CONFIRMATION_FIELD),
            found,
            record,
            RevisionContext(fields, template=template),
        ),
        "review": dict(_saved(found, record, fields, REVIEW_FIELD)),
        "confirmation": dict(_saved(found, record, fields, CONFIRMATION_FIELD)),
    }


def confirmation_draft(
    found: Sequence[Any], record: str, payload: object, writer: str, *, template=None
) -> Any:
    report = confirmation_report(found, record, template=template)
    if report["owed"]:
        raise ProcessEvidenceError(
            "confirm requires a current review: " + ", ".join(str(part) for part in report["owed"]),
            record,
            ("review", "confirm"),
        )
    state = events.fold(found).records[record]
    if not isinstance(payload, dict) or set(payload) != {"checks"}:
        raise ProcessEvidenceError(
            "Completion Confirmation refused: evidence holds the one key checks; "
            + check_shape(completed=True)
        )
    if fault := _check_fault(state.fields, payload["checks"], completed=True):
        raise ProcessEvidenceError(f"Completion Confirmation refused: {fault}")
    _safe_commands(payload["checks"])
    review = report["review"]
    if not isinstance(review, Mapping):
        raise ProcessEvidenceError("confirm requires a recorded review")
    planned = {
        criterion_key(check["criterion"]): check["command"] for check in review.get("checks", [])
    }
    if not small(state.fields) and any(
        planned[criterion_key(check["criterion"])] != check["command"]
        for check in payload["checks"]
    ):
        raise ProcessEvidenceError(
            "Completion Confirmation command argv must match the agreed plan for that criterion"
        )
    return _draft(
        record,
        CONFIRMATION_FIELD,
        {**payload, "revision": report["revision"], "contract": shaping.SHAPING_RULE},
        writer,
    )


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
    complete = _current(
        saved, found, record, RevisionContext(fields, drafts, template)
    ) and _checks(fields, saved.get("checks"), completed=True)
    review = _saved(found, record, fields, REVIEW_FIELD)
    planned = {
        criterion_key(check["criterion"]): check["command"]
        for check in review.get("checks", [])
        if isinstance(check, dict) and "criterion" in check and "command" in check
    }
    complete = complete and (
        small(fields)
        or all(
            planned.get(criterion_key(check["criterion"])) == check["command"]
            for check in saved.get("checks", [])
        )
    )
    return (*missing, *((COMPLETION_HEADING,) if not complete else ()))


def record_process(
    directory: Path | str,
    record: str,
    evidence: object,
    *,
    completed: bool = False,
    redact: Any = None,
) -> list:
    commands = _load("commands")
    admitted, redact = commands.vault_write.admission(directory, redact, commands.environment())
    ledger = commands._ledger(admitted)
    with events.LedgerLock(ledger) as lock:
        commands._require(ledger, record)
        found = events.read_events(ledger)[0]
        builder = confirmation_draft if completed else review_draft
        try:
            draft = builder(
                found,
                record,
                evidence,
                commands.writers.writer_class(os.environ),
                template=commands.templates.load(ledger),
            )
        except ProcessEvidenceError as error:
            raise error.at(Path(directory)) from None
        if isinstance(redact, commands.vault_write.WriteContext) and redact.target is not None:
            saved = json.loads(draft.payload["value"])
            _safe_commands(saved["checks"], commands.vault_write.effective_redactor(redact))
        return commands._append(ledger, [draft], redact, lock)
