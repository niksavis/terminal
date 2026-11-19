from __future__ import annotations

import json
import re
from typing import Any


def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


RECORD = _string("The complete record id returned by the tracker.")
SHAPE = {
    "description": _string("Context and scope. Use a meaningful Context heading."),
    "acceptance": _string("Observable acceptance criteria, one per line."),
    "requirements": _string("Additional constraints."),
    "fields": {"type": "object", "description": "Named tracker fields, such as issue_type."},
}
TOOLS = {
    "ready": ("Read the ranked ready set and holders.", {}, (), True),
    "list": ("Find records in the bound project.", {"query": _string("Search text.")}, (), True),
    "show": (
        "Read a record, its process evidence and history.",
        {
            "record": RECORD,
            "view": {
                "type": "string",
                "enum": ["full", "current", "history"],
                "default": "current",
            },
            "snapshot": _string("The snapshot identity returned by the previous read."),
        },
        ("record",),
        True,
    ),
    "dor": ("Check whether a record is ready to start.", {"record": RECORD}, ("record",), True),
    "fields": ("Read supported tracker fields.", {}, (), True),
    "stats": ("Read project counts.", {}, (), True),
    "blocked": ("Read blocked work and its unmet dependencies.", {}, (), True),
    "refine": ("Read work needing refinement or review.", {}, (), True),
    "create": (
        "Create a record. Review and claim before implementation.",
        {"title": _string("The record title."), **SHAPE},
        ("title",),
        False,
    ),
    "child": (
        "Create a child record under a parent in the bound project.",
        {"parent": RECORD, "title": _string("The child title."), **SHAPE},
        ("parent", "title"),
        False,
    ),
    "update": (
        "Update fields or status through tracker admission.",
        {
            "record": RECORD,
            "status": _string("The requested status."),
            "add_labels": {"type": "array", "items": {"type": "string"}},
            "remove_labels": {"type": "array", "items": {"type": "string"}},
            **SHAPE,
        },
        ("record",),
        False,
    ),
    "comment": (
        "Append a comment without changing the record contract.",
        {"record": RECORD, "text": _string("The comment text.")},
        ("record", "text"),
        False,
    ),
    "review": (
        "Record the confirmation plan before claiming work.",
        {"record": RECORD, "evidence": {"type": "object"}},
        ("record", "evidence"),
        False,
    ),
    "confirm": (
        "Record observed acceptance evidence before completion.",
        {"record": RECORD, "evidence": {"type": "object"}},
        ("record", "evidence"),
        False,
    ),
    "claim": (
        "Claim work. Only a settled successful claim authorizes work.",
        {"record": RECORD},
        ("record",),
        False,
    ),
    "unassign": (
        "Release your claim without taking another holder's claim.",
        {"record": RECORD},
        ("record",),
        False,
    ),
    "close": (
        "Complete a confirmed record with a reason.",
        {
            "record": RECORD,
            "reason": _string("The delivered outcome or cancellation reason."),
            "resolution": {"type": "string", "enum": ["completed", "cancelled"]},
        },
        ("record", "reason"),
        False,
    ),
    "dep": (
        "Add a dependency on another record in the bound project.",
        {
            "record": RECORD,
            "target": RECORD,
            "type": _string("The edge type, such as blocks or parent-child."),
        },
        ("record", "target"),
        False,
    ),
    "undep": (
        "Retract a dependency edge in the bound project.",
        {"record": RECORD, "target": RECORD, "type": _string("The edge type to retract.")},
        ("record", "target"),
        False,
    ),
    "sync": ("Share pending vault writes. Inspect failures before continuing.", {}, (), False),
    "fsck": ("Check integrity without repairing or accepting rewritten history.", {}, (), True),
}


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": f"tracker_{verb}",
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": list(required),
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": readonly,
                "destructiveHint": not readonly,
                "openWorldHint": True,
            },
        }
        for verb, (description, properties, required, readonly) in TOOLS.items()
    ]


def _validate(values: dict[str, Any], properties: dict[str, Any], prefix: str) -> None:
    for key, value in values.items():
        kind = properties[key]["type"]
        expected = {"string": str, "object": dict, "array": list}[kind]
        if not isinstance(value, expected):
            raise ValueError(f"Argument {key} must be a {kind}.")
        if kind == "array" and any(
            not isinstance(label, str) or not label.strip() or "\0" in label for label in value
        ):
            raise ValueError(f"Argument {key} must contain nonempty label strings without NUL.")
        if isinstance(value, str) and "\0" in value:
            raise ValueError(f"Argument {key} must not contain NUL.")
        if "enum" in properties[key] and value not in properties[key]["enum"]:
            raise ValueError(f"Argument {key} must match its declared choices.")
        if key in {"record", "target", "parent"}:
            if not isinstance(value, str) or not re.fullmatch(
                r"[a-z][a-z0-9-]*-[a-z0-9]+(?:\.[a-z0-9]+)*", value
            ):
                raise ValueError(f"Argument {key} must be a record id.")
            if prefix and value.rsplit("-", 1)[0] != prefix:
                raise ValueError(f"Argument {key} belongs to another project.")


def arguments(name: str, values: Any, *, vault: bool, prefix: str) -> list[str]:
    verb = name.removeprefix("tracker_")
    if name != f"tracker_{verb}" or verb not in TOOLS:
        raise ValueError("Unknown tracker tool. Read tools/list.")
    _, properties, required, _ = TOOLS[verb]
    if (
        not isinstance(values, dict)
        or values.keys() - properties.keys()
        or set(required) - values.keys()
    ):
        raise ValueError("Tool arguments do not match its inputSchema.")
    _validate(values, properties, prefix)
    if verb == "update" and "labels" in values.get("fields", {}):
        raise ValueError("Use add_labels and remove_labels to update labels.")
    if verb == "show":
        values = {"view": "current", **values}
    routed = vault and verb in {"claim", "unassign", "comment", "sync", "fsck"}
    argv = [verb] if routed else [verb, ".basicly/ledger"]
    argv.extend(values[key] for key in ("record", "target", "parent") if key in values)
    for key, value in values.items():
        if key in {"record", "target", "parent"}:
            continue
        if key in {"add_labels", "remove_labels"}:
            flag = "--add-label" if key == "add_labels" else "--remove-label"
            argv.extend(f"{flag}={label}" for label in value)
        elif key == "fields":
            for field, content in value.items():
                if not re.fullmatch(r"[a-z][a-z0-9_]*", field):
                    raise ValueError("Field names must be lowercase tracker names.")
                argv.append(f"--field={field}={json.dumps(content, ensure_ascii=False)}")
        elif key == "text" and not routed:
            argv.extend(["--", value])
        else:
            encoded = json.dumps(value, ensure_ascii=False) if key == "evidence" else value
            argv.append(f"--{key}={encoded}")
    return argv
