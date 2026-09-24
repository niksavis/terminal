from __future__ import annotations

import difflib
import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside values.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


fields = _load("fields.py", "basicly_tracker_kit_fields")

WRITABLE_STATUSES = ("open", "in_progress", "blocked", "deferred", "closed")
CLOSED = "closed"
PRIORITY_FIELD = "priority"
PRIORITIES = range(5)
CLOSE_REASON_FIELD = "close_reason"


RefusedValueError = fields.RefusedFieldError


def _status(value: object) -> None:

    if value in WRITABLE_STATUSES:
        return
    near = difflib.get_close_matches(str(value).replace("-", "_"), WRITABLE_STATUSES, n=1)
    hint = f"; did you mean {near[0]!r}?" if near else ""
    raise RefusedValueError(
        f"status {value!r} is not one of {', '.join(WRITABLE_STATUSES)}{hint} "
        f"A record at an unknown status is neither ready nor closed, so it would vanish"
    )


def _priority(value: object) -> None:

    if isinstance(value, int) and not isinstance(value, bool) and value in PRIORITIES:
        return
    raise RefusedValueError(
        f"priority {value!r} is not a whole number from 0 (critical) to 4 (backlog); "
        f"the ready ranking reads it as a number"
    )


def _named(events: Any, draft: Any, name: str) -> bool:
    return draft.kind == events.KIND_FIELD and draft.payload.get("name") == name


def _written_names(events: Any, draft: Any) -> tuple:

    if draft.kind == events.KIND_CREATED:
        return tuple(draft.payload)
    if draft.kind == events.KIND_FIELD:
        return (str(draft.payload.get("name")),)
    return ()


def _written_description(events: Any, draft: Any) -> str:

    if draft.kind == events.KIND_CREATED:
        value = draft.payload.get(fields.shaping.DESCRIPTION_FIELD)
    elif _named(events, draft, fields.shaping.DESCRIPTION_FIELD):
        value = draft.payload.get("value")
    else:
        return ""
    return value if isinstance(value, str) else ""


def _refuse_typed_headings(events: Any, draft: Any) -> None:

    lines = {line.strip() for line in _written_description(events, draft).splitlines()}
    for heading, flag in fields.shaping.TYPED_HEADINGS.items():
        if heading in lines:
            raise RefusedValueError(
                f"the description of {draft.record} holds a {heading!r} heading, which an "
                f"open record never reads; remove it and pass the text as {flag}"
            )


def refuse(events: Any, drafts: Sequence[Any], template: Any = None) -> None:

    reasoned = {
        draft.record
        for draft in drafts
        if (
            _named(events, draft, CLOSE_REASON_FIELD)
            and str(draft.payload.get("value") or "").strip()
        )
        or (
            draft.kind == events.KIND_CREATED
            and str(draft.payload.get(CLOSE_REASON_FIELD) or "").strip()
        )
    }
    for draft in drafts:
        _refuse_typed_headings(events, draft)
        for name in _written_names(events, draft):
            fields.refuse(name, template)
        if draft.kind == events.KIND_STATUS:
            _status(draft.payload.get("status"))
            if draft.payload.get("status") == CLOSED and draft.record not in reasoned:
                raise RefusedValueError(
                    f"closing {draft.record} needs a reason: name what shipped and the evidence, "
                    f"as close --reason; the reason is the permanent record, the diff is not"
                )
        elif _named(events, draft, PRIORITY_FIELD):
            _priority(draft.payload.get("value"))
        elif draft.kind == events.KIND_CREATED and PRIORITY_FIELD in draft.payload:
            _priority(draft.payload[PRIORITY_FIELD])
