from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def file_scoped(
    repo_root: Path,
    entries: Iterable[Mapping[str, Any]],
    checks: list[tuple[str, list[str]]],
    changed: list[str] | None,
    skips: dict[str, str],
) -> list[tuple[str, list[str]]]:
    if changed is None:
        return checks
    suffixes = {
        str(entry["name"]).strip(): entry["staged_suffix"]
        for entry in entries
        if isinstance(entry.get("staged_suffix"), str) and entry["staged_suffix"]
    }
    scoped = []
    for name, command in checks:
        suffix = suffixes.get(name)
        files = [p for p in changed if suffix and p.endswith(suffix) and (repo_root / p).is_file()]
        if suffix and not files:
            skips.setdefault(name, f"no changed {suffix} file")
        scoped.append((name, [*command, *(f"./{p}" if p.startswith("-") else p for p in files)]))
    return scoped


def parse_inputs(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError(f"{label} 'inputs' must be a list of glob strings")
    return tuple(value)
