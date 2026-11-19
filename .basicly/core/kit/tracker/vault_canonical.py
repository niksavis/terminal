from __future__ import annotations

import heapq
import importlib.util
import json
import re
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
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
redact = _load("redact")
fsck = _load("fsck")
process = _load("process_evidence")
recovery = _load("recovery")
REFERENCE = re.compile(r"[a-z][a-z0-9]*-[a-z0-9.-]+#ev-[0-9a-f]{10}(?:-[0-9]+)?")


class CanonicalError(ValueError):
    pass


@dataclass(frozen=True)
class Canonical:
    events: tuple[Any, ...]
    mapping: tuple[Mapping[str, object], ...] = field(repr=False)
    touched: tuple[str, ...]
    reminted: int


def _walk(value: Any, rule: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return rule(value)
    if isinstance(value, dict):
        return {rule(key): _walk(item, rule) for key, item in value.items()}
    if isinstance(value, list):
        return [_walk(item, rule) for item in value]
    return value


def _references(event: Any) -> set[str]:
    return set(REFERENCE.findall(json.dumps([event.payload, event.extra, event.actor])))


def _historical(payload: dict[str, Any]) -> dict[str, Any]:
    if "import_digest" in payload:
        payload = {**payload, "import_digest": "<redacted:source-digest>"}
    if payload.get("name") == "import_digest":
        payload = {**payload, "value": "<redacted:source-digest>"}
    if payload.get("artifact") != recovery.LOSS_ARTIFACT:
        return payload
    body = payload.get("body")
    if not isinstance(body, dict):
        raise CanonicalError(
            "a loss acknowledgment is malformed; repair the source before migration"
        )
    return {
        **payload,
        "artifact": "historical-sequence-loss",
        "body": {key: value for key, value in body.items() if key != "history_sha256"},
    }


def _payload(
    event: Any, rule: Callable[[str], str], names: Mapping[str, str], *, redact_holders: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in _historical(dict(event.payload)).items():
        public_key = names.get(key, rule(key)) if event.kind == events.KIND_CREATED else rule(key)
        if public_key in payload:
            raise CanonicalError(
                "template redaction merges fields; choose a name list without collisions"
            )
        payload[public_key] = _walk(value, rule)
    if event.kind == events.KIND_FIELD and isinstance(event.payload.get("name"), str):
        payload["name"] = names.get(event.payload["name"], payload.get("name"))
    if not redact_holders:
        if event.kind == events.KIND_CREATED and events.HOLDER_FIELD in event.payload:
            payload[events.HOLDER_FIELD] = redact.text(str(event.payload[events.HOLDER_FIELD]))
        elif event.kind == events.KIND_FIELD and event.payload.get("name") == events.HOLDER_FIELD:
            payload["value"] = redact.text(str(event.payload.get("value", "")))
    return payload


def _field_names(
    template: Any, rule: Callable[[str], str], source: Sequence[Any]
) -> dict[str, str]:
    if template is None:
        return {}
    headings = [*template.sections, *(heading for _, group in template.types for heading in group)]
    names = {
        process.shaping.field_of(heading): process.shaping.field_of(rule(heading))
        for heading in headings
    }
    if len(set(names.values())) != len(names):
        raise CanonicalError(
            "template redaction merges fields; choose a name list without collisions"
        )
    for state in events.fold(source).records.values():
        if any(
            old != new and old in state.fields and new in state.fields for old, new in names.items()
        ):
            raise CanonicalError(
                "template redaction overwrites a field; choose a name list without collisions"
            )
    return names


def check(found: Sequence[Any]) -> None:
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder)
        (target / events.INITIAL_LOG_NAME).write_text(
            "".join(events.to_json(event) + "\n" for event in found), encoding="utf-8"
        )
        report = fsck.check(target)
    if not report.clean:
        kinds = sorted({
            finding.kind for finding in report.findings if finding.severity != fsck.WARNING
        })
        raise CanonicalError(
            "ledger integrity refused migration ("
            + ", ".join(kinds)
            + "); run fsck before migration"
        )


def _dependency_order(found: Sequence[Any], template: Any) -> list[Any]:
    by_id = {event.id: event for event in found}
    states, grouped = events.record_index(found)
    semantic: dict[str, set[str]] = {}
    for record, held in states.items():
        headings = process._headings(held, template, False)
        names = process.SEMANTIC_FIELDS | frozenset(
            process.shaping.field_of(one) for one in headings
        )
        semantic[record] = {
            one.id for one in grouped[record] if process._semantic(one, record, names)
        }
    pending: dict[str, set[str]] = {}
    waiting: dict[str, list[str]] = {}
    for event in found:
        dependencies = _references(event) & by_id.keys()
        if event.kind == events.KIND_FIELD and event.payload.get("name") in process.MANAGED_FIELDS:
            dependencies |= semantic[event.record]
            for one in grouped[event.record]:
                if one.kind in (events.KIND_EDGE, events.KIND_EDGE_RETRACTED):
                    target_key, _ = process.labels.DIALECT_KEYS[
                        process.labels.edge_dialect(one.payload)
                    ]
                    dependencies |= semantic.get(one.payload.get(target_key), set())
        pending[event.id] = dependencies
        for dependency in dependencies:
            waiting.setdefault(dependency, []).append(event.id)
    ready = [(events.canonical_key(event), event.id) for event in found if not pending[event.id]]
    heapq.heapify(ready)
    ordered = []
    while ready:
        _, name = heapq.heappop(ready)
        ordered.append(by_id[name])
        for dependent in waiting.get(name, ()):
            pending[dependent].remove(name)
            if not pending[dependent]:
                heapq.heappush(ready, (events.canonical_key(by_id[dependent]), dependent))
    if len(ordered) != len(found):
        raise CanonicalError("event references contain a cycle; resolve it before migration")
    return ordered


@dataclass(frozen=True)
class EvidenceContext:
    source: Sequence[Any]
    transformed: Mapping[str, Any]
    template: Any
    sequences: Mapping[tuple[str, int], int]
    public_template: Any


def _evidence(
    original: Any,
    payload: dict[str, Any],
    actor: str,
    context: EvidenceContext,
) -> dict[str, Any]:
    source, transformed, template, sequences = (
        context.source,
        context.transformed,
        context.template,
        context.sequences,
    )
    name = payload.get("name")
    if original.kind != events.KIND_FIELD or name not in process.MANAGED_FIELDS:
        return payload
    try:
        value = json.loads(payload.get("value", ""))
    except ValueError:
        return {**payload, "value": '{"migration":"invalid-source-evidence"}'}
    except TypeError:
        return {**payload, "value": '{"migration":"invalid-source-evidence"}'}
    if not isinstance(value, dict):
        return {**payload, "value": '{"migration":"invalid-source-evidence"}'}
    report = process.confirmation_report(source, original.record, template=template)
    key = "review" if name == process.REVIEW_FIELD else "confirmation"
    source_fields = events.fold(source).records[original.record].fields
    latest = original.payload.get("value") == source_fields.get(name)
    valid = latest and report[key + "_current"] and bool(report[key])
    if "conversation" in value:
        if process.conversation.fault(source, original.record, value["conversation"]):
            valid = False
        else:
            value["conversation"] = [
                sequences[(original.record, seq)] for seq in value["conversation"]
            ]
    current = [transformed.get(one.id, one) for one in source]
    value["revision"] = (
        process.revision(current, original.record, template=context.public_template)
        if valid
        else "migration-stale"
    )
    if valid:
        value["writer"] = actor
        value["contract"] = process.shaping.SHAPING_RULE
    return {**payload, "value": json.dumps(value, sort_keys=True)}


def canonicalize(
    source: Sequence[Any],
    *,
    redact_holders: bool,
    redactor: Callable[[str], str] | None = None,
    template: Any = None,
    public_template: Any = None,
) -> Canonical:
    check(source)
    found = events.canonical_order(source)
    taken = events.reserved_ids(found)
    mapped: dict[str, str] = {}
    transformed: dict[str, Any] = {}
    sequences: dict[tuple[str, int], int] = {}
    seqs: dict[str, int] = {}
    for one in found:
        seqs[one.record] = seqs.get(one.record, 0) + 1
        sequences[(one.record, one.seq)] = seqs[one.record]
    for index, one in enumerate(found, 1):
        retired = one.payload.get(events.WITHDRAWN_FROM)
        if isinstance(retired, str):
            mapped[retired] = events.event_id_for(
                one.record, events.KIND_WITHDRAWN, {"migration_retired": index}
            )

    def rule(text: str) -> str:
        value = redact.text(text if redactor is None else redactor(text))
        return REFERENCE.sub(lambda match: mapped.get(match[0], match[0]), value)

    rows = []
    touched: set[str] = set()
    reminted = 0
    field_names = _field_names(template, rule, found)
    for one in _dependency_order(found, template):
        payload = _payload(one, rule, field_names, redact_holders=redact_holders)
        actor = rule(one.actor)
        payload = _evidence(
            one,
            payload,
            actor,
            EvidenceContext(
                found,
                transformed,
                template,
                sequences,
                public_template if public_template is not None else template,
            ),
        )
        made = one.id
        if payload != one.payload:
            generation = events.available_generation(one.record, one.kind, payload, taken)
            made = events.event_id_for(one.record, one.kind, payload, generation=generation)
            taken.add(made)
            reminted += 1
        mapped[one.id] = made
        changed = sorted(
            rule("payload." + field_names.get(str(key), str(key)))
            for key in one.payload.keys() | payload.keys()
            if one.payload.get(key) != payload.get(key)
        )
        if actor != one.actor:
            changed.append("actor")
        extra = _walk(dict(one.extra), rule)
        if extra != one.extra:
            changed.append("extra")
        touched.update(changed)
        rows.append({"old": one.id, "new": made, "fields": changed})
        transformed[one.id] = replace(one, id=made, actor=actor, payload=payload, extra=extra)
    totals: dict[str, Any] = {}
    shown = []
    for one in found:
        event = transformed[one.id]
        total = events.accumulate(
            totals.get(one.record, events.Totals()), event.kind, event.payload
        )
        totals[one.record] = total
        shown.append(replace(event, seq=sequences[(one.record, one.seq)], totals=total))
    check(shown)
    shared = "\n".join(events.to_json(one) for one in shown)
    if any(old != new and old in shared for old, new in mapped.items()):
        raise CanonicalError("private event references remain; migration wrote nothing")
    return Canonical(tuple(shown), tuple(rows), tuple(sorted(touched)), reminted)
