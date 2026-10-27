from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

Redact = Callable[[str], str]


def _stored(events: Any, draft: Any, redact: Redact | None) -> dict:
    return events.prepare_payload(draft.payload, kind=draft.kind, redact=redact)


def at_the_generation_a_repeat_needs(
    events: Any, ledger: Path, drafts: Sequence[Any], redact: Redact | None = None
) -> list:

    taken = events.reserved_ids(events.read_events(ledger)[0]) if ledger.is_dir() else set()
    resolved = []
    for draft in drafts:
        stored = _stored(events, draft, redact)
        generation = events.available_generation(draft.record, draft.kind, stored, taken)
        event_id = events.event_id_for(draft.record, draft.kind, stored, generation=generation)
        taken.add(event_id)
        resolved.append(replace(draft, generation=generation))
    return resolved


def _only_repeats(events: Any, existing: Sequence[Any], drafts: Sequence[Any], redact) -> set:

    stated: dict = {}
    for draft in drafts:
        stated.setdefault(draft.record, set()).add(
            events.event_id_for(
                draft.record, draft.kind, _stored(events, draft, redact), generation=1
            )
        )
    newest: dict = {}
    for event in events.canonical_order(list(existing)):
        newest[event.record] = event.id
    return {record for record, ids in stated.items() if newest.get(record) in ids}


def _gate_recurrences(events: Any, existing: Sequence[Any], drafts: Sequence[Any], redact) -> list:

    if not any(draft.kind == events.KIND_GATE for draft in drafts):
        return list(drafts)
    latest: dict = {}
    bounds = events.generation_bounds(existing)
    taken = events.reserved_ids(existing)
    for event in events.canonical_order(list(existing)):
        if event.kind == events.KIND_GATE:
            if not all(isinstance(event.payload.get(name), str) for name in ("gate", "provider")):
                continue
            key = (event.record, event.payload.get("gate"), event.payload.get("provider"))
            latest[key] = (
                events.event_id_for(event.record, event.kind, event.payload, generation=1),
                events.generation_of(event, bounds[event.record]),
            )
    resolved = []
    for draft in drafts:
        if draft.kind != events.KIND_GATE:
            resolved.append(draft)
            continue
        stored = _stored(events, draft, redact)
        if not all(isinstance(stored.get(name), str) for name in ("gate", "provider")):
            raise events.InvalidEventError("a gate recurrence needs a string gate and provider")
        key = (draft.record, stored.get("gate"), stored.get("provider"))
        signature = events.event_id_for(draft.record, draft.kind, stored, generation=1)
        previous = latest.get(key)
        if previous is not None and previous[0] == signature:
            generation = previous[1]
            if generation is None:
                raise events.InvalidEventError(
                    f"{draft.record} has an unminted gate id; repair the ledger before appending"
                )
        else:
            generation = events.available_generation(draft.record, draft.kind, stored, taken)
        event_id = events.event_id_for(draft.record, draft.kind, stored, generation=generation)
        latest[key] = signature, generation
        taken.add(event_id)
        resolved.append(replace(draft, generation=generation))
    return resolved


def at_the_generation_this_write_needs(
    events: Any,
    ledger: Path,
    drafts: Sequence[Any],
    *,
    repeat: bool = False,
    redact: Redact | None = None,
) -> list:

    if repeat:
        return at_the_generation_a_repeat_needs(events, ledger, drafts, redact)
    existing = events.read_events(ledger)[0] if ledger.is_dir() else []
    drafts = _gate_recurrences(events, existing, drafts, redact)
    taken = events.reserved_ids(existing)
    state_kinds = {events.KIND_STATUS, events.KIND_FIELD}
    if not any(
        draft.kind in state_kinds
        and events.event_id_for(
            draft.record, draft.kind, _stored(events, draft, redact), generation=1
        )
        in taken
        for draft in drafts
    ):
        return list(drafts)
    repeated = _only_repeats(events, existing, drafts, redact)
    moving = [
        index
        for index, draft in enumerate(drafts)
        if draft.kind in state_kinds and draft.record not in repeated
    ]
    resolved = list(drafts)
    moved = at_the_generation_a_repeat_needs(events, ledger, [drafts[i] for i in moving], redact)
    for position, draft in enumerate(moved):
        resolved[moving[position]] = draft
    return resolved
