from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside forks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


events = _load("events.py", "basicly_tracker_kit_events")

STATUS_KEY = "status"


class Conflict(NamedTuple):
    record: str
    seq: int
    key: str
    values: tuple[str, ...]


def _setting(event: Any) -> tuple[str, str] | None:

    if event.kind == events.KIND_STATUS:
        return STATUS_KEY, json.dumps(event.payload.get("status"))
    if event.kind == events.KIND_FIELD and isinstance(event.payload.get("name"), str):
        return str(event.payload["name"]), json.dumps(event.payload.get("value"))
    return None


def forked_groups(ordered: Iterable[Any]) -> dict[tuple[str, int], list[Any]]:

    claimed: dict[tuple[str, int], list[Any]] = {}
    for event in ordered:
        claimed.setdefault((event.record, event.seq), []).append(event)
    return {key: found for key, found in claimed.items() if len(found) > 1}


def conflicts(ordered: Sequence[Any]) -> list[Conflict]:

    settings: dict[str, list[tuple[int, str]]] = {}
    for event in ordered:
        setting = _setting(event)
        if setting is not None:
            settings.setdefault(event.record, []).append((event.seq, setting[0]))
    found: list[Conflict] = []
    for (record, seq), group in sorted(forked_groups(ordered).items()):
        values: dict[str, set[str]] = {}
        for event in group:
            setting = _setting(event)
            if setting is not None:
                values.setdefault(setting[0], set()).add(setting[1])
        for key, seen in sorted(values.items()):
            restated = any(later > seq and name == key for later, name in settings.get(record, []))
            if len(seen) > 1 and not restated:
                found.append(Conflict(record, seq, key, tuple(sorted(seen))))
    return found


def of_record(ordered: Sequence[Any], record: str) -> list[dict[str, object]]:
    return [
        {"key": one.key, "seq": one.seq, "values": [json.loads(value) for value in one.values]}
        for one in conflicts([event for event in ordered if event.record == record])
    ]
