from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load() -> Any:
    name = "basicly_tracker_kit_git_runner"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _HERE / "git_runner.py")
    if spec is None or spec.loader is None:
        raise ImportError("git_runner.py is missing from beside vault_private.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load()


class PrivateMapError(ValueError):
    pass


@dataclass(frozen=True)
class Destination:
    path: Path = field(repr=False)
    clone: Any = field(repr=False)
    overwrite: bool = False


def _common(directory: Path) -> Path | None:
    try:
        text = git_runner.run(["rev-parse", "--git-common-dir"], directory).strip()
    except git_runner.GitCommandError as exc:
        ancestors = (directory, *directory.parents)
        marked = any(
            (parent / ".git").exists()
            or ((parent / "HEAD").is_file() and (parent / "objects").is_dir())
            for parent in ancestors
        )
        if exc.returncode != 128 or marked:
            raise PrivateMapError(
                "private map repository could not be checked; choose another folder"
            ) from None
        return None
    return (directory / text).resolve()


def _local_source(url: str) -> Path | None:
    if url.startswith("file:"):
        if not url.startswith("file://"):
            return None
        raw = re.sub(
            rb"%([0-9A-Fa-f]{2})",
            lambda match: bytes([int(match[1], 16)]),
            url[7:].encode("utf-8", errors="surrogateescape"),
        )
        text = os.fsdecode(raw)
        if not text.startswith("/"):
            text = "//" + text
        if os.name == "nt" and len(text) > 2 and text[0] == "/" and text[2] == ":":
            text = text[1:]
        return Path(text).resolve()
    candidate = Path(url)
    return candidate.resolve() if "://" not in url and candidate.is_dir() else None


def _same_vault(directory: Path, common: Path, clone: Any) -> bool:
    local = _local_source(clone.url)
    origins = [clone.bare.resolve()]
    if local is not None:
        origins.append(local)
    for origin in origins:
        if origin.is_dir() and _common(origin) == common:
            return True
    try:
        url = git_runner.run(["config", "--get", "remote.origin.url"], directory).strip()
    except git_runner.GitCommandError as exc:
        if exc.returncode == 1:
            return False
        raise PrivateMapError(
            "private map repository could not be checked; choose another folder"
        ) from None
    linked = _local_source(url)
    return url.rstrip("/") == clone.url.rstrip("/") or (
        linked is not None and local is not None and linked == local
    )


def prepare(path: Path, clone: Any, *, overwrite: bool = False) -> Destination:
    try:
        resolved = path.expanduser().resolve()
        parent = resolved.parent
        if not parent.is_dir():
            raise PrivateMapError(
                "private map parent does not exist; create a private folder first"
            )
        if resolved.exists() and (not overwrite or not resolved.is_file()):
            raise PrivateMapError(
                "private map already exists; use --overwrite-private-map for a file"
            )
        common = _common(parent)
        if common is not None:
            if resolved.is_relative_to(common) or _same_vault(parent, common, clone):
                raise PrivateMapError(
                    "private map is inside the vault repository; choose a private folder outside it"
                )
            try:
                git_runner.run(["check-ignore", "-q", "--", str(resolved)], parent)
            except git_runner.GitCommandError:
                raise PrivateMapError(
                    "private map is not ignored by its repository; "
                    "choose a private folder outside it"
                ) from None
        return Destination(resolved, clone, overwrite)
    except OSError:
        raise PrivateMapError(
            "private map destination could not be checked; choose another private folder"
        ) from None
    except RuntimeError:
        raise PrivateMapError(
            "private map destination could not be checked; choose another private folder"
        ) from None
    except git_runner.GitRunnerError:
        raise PrivateMapError(
            "private map destination could not be checked; choose another private folder"
        ) from None


def write(destination: Destination, rows: Sequence[Mapping[str, object]]) -> None:
    checked = prepare(destination.path, destination.clone, overwrite=destination.overwrite)
    if checked.path != destination.path:
        raise PrivateMapError("private map destination changed; choose another private folder")
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".migration-map-", dir=destination.path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {"format": 1, "events": list(rows)}, handle, sort_keys=True, ensure_ascii=False
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if destination.overwrite:
            temporary.replace(destination.path)
        else:
            os.link(temporary, destination.path)
    except OSError:
        raise PrivateMapError(
            "private map could not be saved; check its destination and permissions"
        ) from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
