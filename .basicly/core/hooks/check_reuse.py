from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import subprocess  # nosec B404
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

STORE = Path(".basicly/usage/check-passes.json")
KEEP = 400


def _git(root: Path, *args: str) -> str | None:
    done = subprocess.run(  # nosec B603 B607
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=False
    )
    return done.stdout if done.returncode == 0 else None


def key(root: Path, interpreter: str | None) -> str | None:
    if os.environ.get("CI") or not os.environ.get("BASICLY_SNAPSHOT_TREE") or not interpreter:
        return None
    listed = _git(root, "ls-files", "--others", "--exclude-standard")
    tree = _git(root, "write-tree")
    linked = set(os.environ.get("BASICLY_SNAPSHOT_LINKS", "").splitlines())
    if listed is None or set(listed.splitlines()) - linked or not tree:
        return None
    return f"{tree.strip()}:{interpreter}"


@cache
def matcher(globs: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        "|".join(f"(?:{glob.translate(g, recursive=True, include_hidden=True)})" for g in globs)
    )


def input_keys(
    root: Path, at: str | None, checks: Sequence[tuple[str, list[str], list[str]]]
) -> dict[str, str]:
    listed = _git(root, "ls-files", "-s", "-z") if at is not None and checks else None
    if listed is None or at is None:
        return {}
    entries = [line.partition("\t") for line in listed.split("\0") if line]
    interpreter = at.partition(":")[2]
    keys: dict[str, str] = {}
    for name, command, globs in checks:
        digest = hashlib.sha256(json.dumps([name, command, interpreter]).encode())
        pattern = matcher(tuple(globs))
        for meta, _, path in entries:
            if pattern.match(path):
                digest.update(f"{meta}\t{path}\0".encode())
        keys[name] = f"inputs:{digest.hexdigest()}"
    return keys


def _load(root: Path) -> dict[str, dict]:
    try:
        held = json.loads((root / STORE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return held if isinstance(held, dict) else {}


def passed(root: Path, at: str | None) -> frozenset[str]:
    entry = _load(root).get(at or "")
    names = entry.get("checks") if isinstance(entry, dict) else None
    return frozenset(str(name) for name in names) if isinstance(names, list) else frozenset()


def record(root: Path, passes: Mapping[str, list[str]]) -> None:
    if not passes:
        return
    held = _load(root)
    now = datetime.now(UTC).isoformat()
    for at, names in passes.items():
        held[at] = {"checks": sorted(set(names) | passed(root, at)), "at": now}
    kept = dict(sorted(held.items(), key=lambda item: str(item[1].get("at", "")))[-KEEP:])
    path = root / STORE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        marker = path.parent / ".gitignore"
        if not marker.exists():
            marker.write_text("*\n", encoding="utf-8")
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError:
        return
