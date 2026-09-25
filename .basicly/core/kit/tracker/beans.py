from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside beans.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


migrate = _load("migrate.py", "basicly_tracker_kit_migrate")

BEANS_DIR = ".beans"
ARCHIVE_DIR = "archive"
FENCE = "---"
ID_SEPARATOR = "--"
CLOSED = "closed"

VOCABULARY = {
    "status": {
        "todo": {"status": "open"},
        "in-progress": {"status": "in_progress"},
        "draft": {"status": "deferred"},
        "completed": {"status": CLOSED, "close_reason": "completed in beans"},
        "scrapped": {"status": CLOSED, "close_reason": "scrapped in beans"},
    },
    "type": {
        "milestone": {"issue_type": "epic", "labels": ["milestone"]},
        "epic": {"issue_type": "epic"},
        "bug": {"issue_type": "bug"},
        "feature": {"issue_type": "feature"},
        "task": {"issue_type": "task"},
    },
    "priority": {
        "critical": {"priority": 0},
        "high": {"priority": 1},
        "normal": {"priority": 2},
        "low": {"priority": 3},
        "deferred": {"priority": 4},
    },
}
FILLED_WHEN_ABSENT = {"type": "task", "priority": "normal"}

KEPT_KEYS = ("title", "created_at", "updated_at", "order")
SCALAR_KEYS = frozenset({*VOCABULARY, *KEPT_KEYS, "parent"})
LIST_KEYS = frozenset({"tags", "blocking", "blocked_by"})

PARENT_EDGE = "parent-child"
BLOCKS_EDGE = "blocks"

_KEY_LINE = re.compile(r"^([a-z_]+):(?: (.*))?$")
_ITEM_LINE = re.compile(r"^ *- (\S.*)$")
_INDICATORS = frozenset("[]{}&*!|>%@`#,")
_NOT_A_STRING = re.compile(
    r"^(?:~|null|true|false|yes|no|on|off|y|n|[-+]?(?:\d[\d_]*)?\.?\d+(?:e[-+]?\d+)?"
    r"|0x[0-9a-f]+|0o[0-7]+|[-+]?\.inf|\.nan)$",
    re.IGNORECASE,
)


class BeansFormError(migrate.SnapshotError):
    pass


def _refused(where: str, reason: str) -> BeansFormError:
    return BeansFormError(f"beans file {where} {reason}; no bean of the batch was imported")


def _scalar(raw: str, where: str) -> str:

    if raw.startswith("'"):
        inner = raw[1:-1]
        if len(raw) < 2 or not raw.endswith("'") or "'" in inner.replace("''", ""):
            raise _refused(where, f"holds the single-quoted value {raw!r}, which does not close")
        return inner.replace("''", "'")
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise _refused(where, f"holds the double-quoted value {raw!r}: {exc}") from exc
        if not isinstance(value, str):
            raise _refused(where, f"holds the value {raw!r}, which is not one string")
        return value
    if raw[0] in _INDICATORS or ": " in raw or " #" in raw or raw.endswith(":"):
        raise _refused(where, f"holds the value {raw!r} in a YAML form this reader does not know")
    if _NOT_A_STRING.match(raw):
        raise _refused(where, f"holds the plain value {raw!r}, which YAML reads as no string")
    return raw


def _frontmatter(lines: list[str], where: str) -> dict[str, Any]:

    found: dict[str, Any] = {}
    listing: list[str] | None = None
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        item = _ITEM_LINE.match(line)
        if item is not None and listing is not None:
            listing.append(_scalar(item.group(1).strip(), where))
            continue
        pair = _KEY_LINE.match(line)
        if pair is None:
            raise _refused(where, f"holds the line {line!r}, a form this reader does not know")
        key, raw = pair.group(1), (pair.group(2) or "").strip()
        if key in found:
            raise _refused(where, f"names the key {key!r} twice")
        if key in LIST_KEYS:
            if raw:
                raise _refused(where, f"holds {key} as {raw!r}; this reader knows a block list")
            listing = found[key] = []
        elif key in SCALAR_KEYS:
            listing = None
            found[key] = _scalar(raw, where) if raw else ""
        else:
            known = ", ".join(sorted(SCALAR_KEYS | LIST_KEYS))
            raise _refused(where, f"names the key {key!r}, which is not one of {known}")
    return found


def _split(text: str, where: str) -> tuple[dict[str, Any], str]:

    lines = text.split("\n")
    if lines[0] != FENCE:
        raise _refused(where, f"does not open with a {FENCE} frontmatter fence")
    if FENCE not in lines[1:]:
        raise _refused(where, f"has no closing {FENCE} frontmatter fence")
    end = lines.index(FENCE, 1)
    return _frontmatter(lines[1:end], where), "\n".join(lines[end + 1 :]).strip("\n")


def _record(bean: str, found: dict[str, Any], body: str, where: str, archived: bool) -> dict:

    record: dict[str, Any] = {"id": bean}
    labels = list(found.get("tags", []))
    for key, table in VOCABULARY.items():
        if key not in found and key not in FILLED_WHEN_ABSENT:
            raise _refused(where, f"has no {key}")
        value = found.get(key, FILLED_WHEN_ABSENT.get(key))
        mapped = table.get(value)
        if mapped is None:
            raise _refused(where, f"holds {key} {value!r}, which is not one of {', '.join(table)}")
        labels.extend(mapped.get("labels", []))
        record.update({name: one for name, one in mapped.items() if name != "labels"})
    record.update({key: found[key] for key in KEPT_KEYS if found.get(key)})
    if labels:
        record["labels"] = list(dict.fromkeys(labels))
    record["description"] = body
    if archived and record["status"] != CLOSED:
        record["status"] = CLOSED
        record["close_reason"] = f"archived in beans at status {found['status']}"
    return record


def _links(bean: str, found: dict[str, Any]) -> list[tuple[str, str, str, str]]:

    links = [(bean, target, BLOCKS_EDGE, target) for target in found.get("blocked_by", [])]
    links += [(holder, bean, BLOCKS_EDGE, holder) for holder in found.get("blocking", [])]
    if found.get("parent"):
        links.append((bean, found["parent"], PARENT_EDGE, found["parent"]))
    return links


def bean_files(path: Path | str) -> tuple[Path, list[Path]]:

    given = Path(path)
    folder = given / BEANS_DIR if (given / BEANS_DIR).is_dir() else given
    files = [
        file
        for file in sorted(folder.rglob("*.md"))
        if not any(part.startswith(".") for part in file.relative_to(folder).parts[:-1])
    ]
    if not files:
        raise BeansFormError(
            f"{given} holds no beans backlog: name the repository root that holds {BEANS_DIR}, "
            f"or the {BEANS_DIR} folder itself"
        )
    return folder, files


def read_snapshot(path: Path | str, *, name: str | None = None) -> Any:

    folder, files = bean_files(path)
    named = migrate.validate_source_name(folder.name if name is None else name)
    records: dict[str, dict] = {}
    held_in: dict[str, str] = {}
    links: list[tuple[str, tuple[str, str, str, str]]] = []
    digest = hashlib.sha256()
    for file in files:
        parts = file.relative_to(folder).parts
        where = "/".join(parts)
        bean, separator, _slug = file.name.removesuffix(".md").partition(ID_SEPARATOR)
        if not bean or not separator:
            raise _refused(where, f"is not named <id>{ID_SEPARATOR}<slug>.md")
        if bean in held_in:
            raise _refused(where, f"holds the id {bean}, which {held_in[bean]} also holds")
        text = file.read_text(encoding="utf-8")
        digest.update(f"{where}\0{text}\0".encode())
        found, body = _split(text, where)
        records[bean] = _record(bean, found, body, where, parts[0] == ARCHIVE_DIR)
        held_in[bean] = where
        links.extend((where, link) for link in _links(bean, found))
    for where, (holder, target, kind, named_id) in links:
        if named_id not in records:
            raise _refused(where, f"links to {named_id!r}, which no bean in {folder.name} holds")
        edge = {"issue_id": holder, "depends_on_id": target, "type": kind}
        records[holder].setdefault("dependencies", []).append(edge)
    return migrate.Snapshot(
        name=named, digest=digest.hexdigest(), records=tuple(records.values()), unreadable=()
    )


READERS = {"beads": migrate.read_snapshot, "beans": read_snapshot}
