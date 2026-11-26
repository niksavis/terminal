from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside closing.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


events = _load("events.py", "basicly_tracker_kit_events")
landing = _load("landing_evidence.py", "basicly_tracker_kit_landing_evidence")
evidence_checks = _load("evidence_checks.py", "basicly_tracker_kit_evidence_checks")

FOLLOWUP_FIELD = "followup_of"
SUPERSEDED_FIELD = "superseded_by"
EDGE = "discovered-from"
LANDED_USAGE = "close --landed COMMIT --tests JSON closes one record; give both"


@dataclass(frozen=True)
class Ending:
    reason: str = ""
    resolution: str = "completed"
    landed: str = ""
    tests: str = ""
    superseded_by: str = ""


def _root() -> Path:
    return Path(landing._git(["rev-parse", "--show-toplevel"], Path.cwd()).strip())


def evidence(state: Any, landed: str, tests: str) -> str:
    try:
        mapped = json.loads(tests)
    except ValueError:
        raise landing.LandingEvidenceError("--tests must be a JSON object") from None
    if not isinstance(mapped, dict):
        raise landing.LandingEvidenceError("--tests must map each criterion to a path or null")
    criteria = evidence_checks.criteria(state.fields)
    artifact = state.artifacts.get(landing.ARTIFACT)
    found = landing.gather(_root(), landed, artifact, mapped, criteria)
    return json.dumps(found, sort_keys=True)


def superseded(states: Mapping[str, Any], target: str) -> str:
    held = states.get(target)
    if held is not None and not held.tombstoned:
        return target
    try:
        landing._git(["rev-parse", "-q", "--verify", f"refs/tags/{target}"], _root())
    except landing.LandingEvidenceError:
        raise landing.LandingEvidenceError(
            f"--superseded-by {target!r} names no record and no tag; name the record or the "
            "release tag that replaced it"
        ) from None
    return target


def children(found: Sequence[Any]) -> dict[str, list[str]]:
    held: dict[str, set[str]] = {}
    for event in found:
        payload = event.payload
        if payload.get("type") != "parent-child":
            continue
        kids = held.setdefault(str(payload.get("to", "")), set())
        if event.kind == events.KIND_EDGE:
            kids.add(event.record)
        elif event.kind == events.KIND_EDGE_RETRACTED:
            kids.discard(event.record)
    return {parent: sorted(kids) for parent, kids in held.items()}


def open_followups(
    states: Mapping[str, Any], children: Mapping[str, Sequence[str]], record: str
) -> list[str]:
    family = set(children.get(record, ()))
    return sorted(
        key
        for key, state in states.items()
        if not state.tombstoned
        and state.status != "closed"
        and state.fields.get(FOLLOWUP_FIELD) in family
    )


def run(args: Any, context: Any, commands: Any) -> list:
    landed = getattr(args, "landed", None)
    if landed is not None and (not getattr(args, "tests", None) or len(args.record) != 1):
        raise landing.LandingEvidenceError(LANDED_USAGE)
    ending = Ending(
        reason=args.reason,
        resolution=args.resolution,
        landed=landed or "",
        tests=getattr(args, "tests", None) or "",
        superseded_by=getattr(args, "superseded_by", "") or "",
    )
    appended = commands.close_with(args.directory, args.record, ending=ending, context=context)
    if landed is None:
        return appended
    record = args.record[0]
    value = next(
        (
            event.payload.get("value")
            for event in appended
            if event.kind == events.KIND_FIELD and event.payload.get("name") == landing.FIELD
        ),
        {},
    )
    for criterion in landing.untested(value):
        appended += _followup(args.directory, record, criterion, context, commands)
    return appended


def _followup(directory: Any, record: str, criterion: str, context: Any, commands: Any) -> list:
    fields = {
        "title": f"Add a test for a criterion of {record}"[:200],
        "issue_type": "task",
        "priority": 3,
        FOLLOWUP_FIELD: record,
        "description": (
            f"## Context\n\n{record} closed by landing evidence, but no test checks this "
            f"criterion: {criterion}"
        ),
        "acceptance_criteria": f"A test checks: {criterion}",
    }
    prefix = record.split("-", 1)[0]
    made = commands.create_root(directory, fields, prefix=prefix, context=context)
    new = made[0].record
    return [
        *made,
        *commands.add_dependency(directory, new, record, edge_type=EDGE, context=context),
    ]
