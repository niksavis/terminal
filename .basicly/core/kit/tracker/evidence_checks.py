from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Mapping
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


shaping = _load("shaping")
_PLACEHOLDER = re.compile(r"(?:todo|tbd|tbc|fixme)", re.IGNORECASE)
_LIST_MARKER = re.compile(r"^(?:[-*]|\d+[.)])\s+(?:\[[ xX]\]\s*)?")


def filled_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(re.search(r"[^\W_]", value))
        and not shaping.unfilled(value)
        and not _PLACEHOLDER.fullmatch(value.strip(" ,.:;!?-_"))
    )


def criterion_key(text: object) -> str:
    return _LIST_MARKER.sub("", str(text).strip())


def criteria(fields: Mapping[str, object]) -> tuple[str, ...]:
    value = fields.get("acceptance_criteria")
    entries = (
        value.splitlines()
        if isinstance(value, str)
        else value
        if isinstance(value, (list, tuple))
        else ()
    )
    return tuple(
        criterion_key(entry) for entry in entries if isinstance(entry, str) and entry.strip()
    )


def filled_command(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and isinstance(value[0], str)
        and bool(value[0].strip())
        and all(isinstance(part, str) and not shaping.unfilled(part) for part in value)
    )


PLANNED_CHECK_KEYS = ("criterion", "command", "expected")
COMPLETED_CHECK_KEYS = ("criterion", "command", "result", "exit_code")


def check_shape(*, completed: bool = False) -> str:
    keys = COMPLETED_CHECK_KEYS if completed else PLANNED_CHECK_KEYS
    return "each check holds exactly the keys " + ", ".join(keys) + "; command is an argv list"


def entry_fault(check: object, keys: set[str], completed: bool) -> str | None:
    if not isinstance(check, dict):
        return "is not an object"
    parts = [f"lacks the key {', '.join(sorted(keys - set(check)))}"] if keys - set(check) else []
    if extra := sorted(set(check) - keys):
        parts.append(f"holds the unknown key {', '.join(extra)}")
    if parts:
        return " and ".join(parts) + "; " + check_shape(completed=completed)
    faults = (
        (not filled_text(check["criterion"]), "has no criterion text"),
        (not filled_command(check["command"]), "command is not a filled argv list of strings"),
        (completed and not filled_text(check["result"]), "has no observed result text"),
        (
            completed and (type(check["exit_code"]) is not int or check["exit_code"] != 0),
            "exit_code is not the integer 0",
        ),
        (not completed and not filled_text(check["expected"]), "has no expected result text"),
    )
    return next((text for failed, text in faults if failed), None)


def check_fault(
    fields: Mapping[str, object], checks: object, *, completed: bool = False
) -> str | None:
    expected = criteria(fields)
    if not expected or len(set(expected)) != len(expected):
        return "the record holds no unique acceptance criteria"
    if not isinstance(checks, list):
        return "checks must be a list"
    keys: set[str] = set(COMPLETED_CHECK_KEYS if completed else PLANNED_CHECK_KEYS)
    for index, check in enumerate(checks):
        if fault := entry_fault(check, keys, completed):
            return f"check {index} {fault}"
    held = [criterion_key(check["criterion"]) for check in checks]
    listed = "; the record holds the criteria " + ", ".join(repr(item) for item in expected)
    faults = (
        ([item for item in held if held.count(item) > 1], "checks repeat the criterion", ""),
        ([item for item in held if item not in expected], "no acceptance criterion reads", listed),
        ([item for item in expected if item not in held], "no check covers the criterion", ""),
    )
    return next((f"{text} {items[0]!r}{tail}" for items, text, tail in faults if items), None)
