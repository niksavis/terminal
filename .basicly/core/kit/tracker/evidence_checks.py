from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
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


shaping = _load("shaping")
_PLACEHOLDER = re.compile(r"(?:todo|tbd|tbc|fixme)", re.IGNORECASE)
_LIST_MARKER = re.compile(r"^(?:[-*]|\d+[.)])\s+(?:\[[ xX]\]\s*)?")
_REDACTION = re.compile(r"<redacted:[a-z][a-z0-9-]*>")
_NOT_RUN = re.compile(
    r"\b(?:pending|not\s+(?:yet\s+)?run|not\s+yet|has\s+not\s+run|did\s+not\s+run|"
    r"will\s+(?:be\s+)?run|to\s+be\s+run|verified\s+after)\b",
    re.IGNORECASE,
)


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


def observed_text(value: object) -> bool:
    return isinstance(value, str) and filled_text(_REDACTION.sub("", value))


PLANNED_CHECK_KEYS = ("criterion", "command", "expected")
COMPLETED_CHECK_KEYS = ("criterion", "command", "result", "exit_code")
_SAMPLE = {
    "criterion": "the criterion text",
    "command": ["uv", "run", "pytest", "-q"],
    "expected": "what the command shows when it passes",
    "result": "what the command printed",
    "exit_code": 0,
}
_EVIDENCE = {"review": PLANNED_CHECK_KEYS, "confirm": COMPLETED_CHECK_KEYS}


def _shown(path: Path) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:
        return str(path)


class NextStepsError(Exception):
    def __init__(
        self, text: str, record: str = "", steps: Sequence[str] = (), ledger: Path | None = None
    ) -> None:
        told = f"{text}; {next_commands(record, steps, ledger)}" if steps else text
        super().__init__(told)
        self.text, self.record, self.steps = text, record, tuple(steps)

    def at(self, ledger: Path) -> NextStepsError:
        return type(self)(self.text, self.record, self.steps, ledger)


def next_commands(record: str, verbs: Sequence[str], ledger: Path | None = None) -> str:
    tool = _load("locate").typed_in(_HERE / "cli.py", Path.cwd()).split(" ")
    place = _shown(ledger) if ledger is not None else ".basicly/ledger"
    shown = []
    for verb in verbs:
        words = [*tool, verb, place, record]
        if verb in _EVIDENCE:
            check = {key: _SAMPLE[key] for key in _EVIDENCE[verb]}
            words += ["--evidence", json.dumps({"checks": [check]})]
        if verb == "close":
            words += ["--reason", "what was delivered"]
        shown.append(shlex.join(words))
    return "next: " + ", then ".join(shown)


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
        (completed and not observed_text(check["result"]), "has no observed result text"),
        (
            completed and bool(_NOT_RUN.search(str(check["result"]))),
            "result says the check has not run; run the command and record what it printed",
        ),
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


def command_privacy_fault(
    checks: Sequence[Mapping[str, Any]], redactor: Callable[[str], str] | None = None
) -> str | None:
    rules = _load("beads").MACHINE_PATH_RULES
    if any(
        any(pattern.search(part) for _name, pattern in rules)
        or (redactor is not None and redactor(part) != part)
        for check in checks
        for part in check["command"]
    ):
        return (
            "Evidence command holds a machine path or private value that redaction would change. "
            "Use python3 on PATH and paths relative to the repository."
        )
    return None
