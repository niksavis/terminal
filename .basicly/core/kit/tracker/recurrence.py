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

    taken = {event.id for event in events.read_events(ledger)[0]} if ledger.is_dir() else set()
    resolved = []
    for draft in drafts:
        stored = _stored(events, draft, redact)
        generation = 1
        event_id = events.event_id_for(draft.record, draft.kind, stored, generation=generation)
        while event_id in taken:
            generation += 1
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
    taken = {event.id for event in existing}
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
