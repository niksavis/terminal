from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Mapping
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
        raise ImportError(f"the tracker kit's {file_name} is missing from beside beads.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


values = _load("values.py", "basicly_tracker_kit_values")

WORK_TYPES = ("bug", "chore", "task", "feature", "epic")

STATUS_FIELD = "status"
TYPE_FIELD = values.fields.shaping.TYPE_FIELD
LINE_KIND_FIELD = "_type"
ISSUE_LINE = "issue"
MACHINE_PATH_FIELDS = frozenset({"source_repo_path"})

_PATH_TAIL = r"[^\s\"'`,;)\]}]*"

MACHINE_PATH_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("posix-home-path", re.compile(rf"/(?:home|Users)/[A-Za-z0-9._-]+{_PATH_TAIL}")),
    ("windows-unc-path", re.compile(rf"\\\\\?\\[A-Za-z]:\\{_PATH_TAIL}")),
    ("windows-drive-path", re.compile(rf"[A-Za-z]:\\{_PATH_TAIL}")),
)

_SAME_STATUSES = {status: status for status in values.WRITABLE_STATUSES}
_SAME_TYPES = {kind: kind for kind in WORK_TYPES}


@dataclass(frozen=True)
class Source:
    name: str
    statuses: Mapping[str, str]
    types: Mapping[str, str]
    envelope: frozenset[str]


BD = Source(
    name="bd",
    statuses={**_SAME_STATUSES, "pinned": "deferred", "hooked": "in_progress"},
    types={
        **_SAME_TYPES,
        "decision": "chore",
        "spike": "chore",
        "story": "feature",
        "milestone": "epic",
    },
    envelope=frozenset({
        LINE_KIND_FIELD,
        "dependency_count",
        "dependent_count",
        "comment_count",
        "parent",
        "wisp_plane",
    }),
)

BR = Source(
    name="br",
    statuses={**_SAME_STATUSES, "draft": "deferred", "pinned": "deferred"},
    types={
        **_SAME_TYPES,
        "docs": "chore",
        "question": "chore",
        "feat": "feature",
        "research-spike": "chore",
    },
    envelope=frozenset(),
)

_DELETION_STATUS = "tombstone"


def _redacted(value: object) -> object:

    if isinstance(value, str):
        for rule, pattern in MACHINE_PATH_RULES:
            value = pattern.sub(f"<redacted:{rule}>", value)
        return value
    if isinstance(value, dict):
        return {key: _redacted(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted(item) for item in value]
    return value


def _source_of(raw: Mapping[str, object]) -> Source:

    return BD if LINE_KIND_FIELD in raw else BR


def _line_refusal(raw: Mapping[str, object]) -> str:

    kind = raw.get(LINE_KIND_FIELD, ISSUE_LINE)
    if kind == ISSUE_LINE:
        return ""
    if kind == "memory":
        return "a bd memory line, not an issue: export again without --include-memories"
    return f"a bd {kind!r} line, not an issue: only {LINE_KIND_FIELD} {ISSUE_LINE!r} is a record"


def _value_refusal(record: object, source: Source, name: str, value: str) -> str:

    if name == STATUS_FIELD and value == _DELETION_STATUS:
        return (
            f"{record!r} is at status {value!r}, which marks a deletion in {source.name}: it is "
            f"not imported, a record this ledger already holds is reported absent, and the "
            f"tracker's delete command tombstones it"
        )
    table = source.statuses if name == STATUS_FIELD else source.types
    targets = values.WRITABLE_STATUSES if name == STATUS_FIELD else WORK_TYPES
    return (
        f"{record!r} has {name} {value!r}, which the {source.name} table does not map: it maps "
        f"{', '.join(sorted(table))} onto {', '.join(targets)}; change it in {source.name} "
        f"and export again"
    )


def normalize(raw: Mapping[str, object]) -> tuple[dict[str, object] | None, str]:

    refused = _line_refusal(raw)
    if refused:
        return None, refused
    source = _source_of(raw)
    dropped = source.envelope | MACHINE_PATH_FIELDS
    record = {key: _redacted(value) for key, value in raw.items() if key not in dropped}
    for name, table in ((STATUS_FIELD, source.statuses), (TYPE_FIELD, source.types)):
        value = record.get(name)
        if not isinstance(value, str) or not value:
            continue
        mapped = table.get(value)
        if mapped is None:
            return None, _value_refusal(raw.get("id"), source, name, value)
        record[name] = mapped
    return record, ""
