from __future__ import annotations

from collections.abc import Mapping

HEADING = "## Small Task"
SIZE_FIELD = "size"
SMALL = "small"
TYPES = ("task", "bug", "chore")


def small(fields: Mapping[str, object]) -> bool:
    return fields.get(SIZE_FIELD) == SMALL


def fault(fields: Mapping[str, object], criteria: int) -> str:
    if fields.get("issue_type") not in TYPES:
        return "size=small needs issue_type task, bug or chore"
    if criteria != 1:
        return "size=small needs exactly one acceptance criterion"
    return ""


def owed(fields: Mapping[str, object], criteria: int) -> tuple[str, ...]:
    broken = fault(fields, criteria)
    return (f"{HEADING}: {broken}",) if broken else ()
