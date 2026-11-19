from __future__ import annotations

import importlib.util
import sys
from collections.abc import Collection
from pathlib import Path
from typing import Any


def _load(name: str) -> Any:
    key = "basicly_tracker_kit_" + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name(name + ".py"))
    if spec is None or spec.loader is None:
        raise ImportError(name + ".py is missing from beside vault_citations.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner")
canonical = _load("vault_canonical")


def census(directory: Path, changed: Collection[str]) -> dict[str, object]:
    try:
        root = Path(git_runner.run(["rev-parse", "--show-toplevel"], directory).strip())
        names = git_runner.run(["ls-files", "-z"], root).split("\0")
        messages = git_runner.run(["log", "--format=%B"], root)
    except git_runner.GitRunnerError:
        return {"available": False, "scope": "tracked-files-and-head-history"}
    private = set(changed)

    def count(text: str) -> int:
        return sum(match in private for match in canonical.REFERENCE.findall(text))

    matched = 0
    citations = 0
    examined = 0
    unreadable = 0
    for name in names:
        relative = Path(name)
        if not name or any(part.startswith(".env") for part in relative.parts):
            continue
        if relative.parts[:2] == (".basicly", "ledger"):
            continue
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            unreadable += 1
            continue
        try:
            body = path.read_bytes()
            if b"\0" in body:
                continue
            text = body.decode("utf-8")
        except OSError:
            unreadable += 1
            continue
        except UnicodeError:
            unreadable += 1
            continue
        examined += 1
        number = count(text)
        citations += number
        matched += bool(number)
    return {
        "available": True,
        "scope": "tracked-files-and-head-history",
        "files_examined": examined,
        "files_unreadable": unreadable,
        "files_with_citations": matched,
        "file_citations": citations,
        "commit_citations": count(messages),
    }
