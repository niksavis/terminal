from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import unquote

_HERE = Path(__file__).resolve().parent
API = "/api/v1"
READS = ("ready", "blocked", "stats", "fields", "refine", "scaffold")

TRACKER_DIR = _HERE.parent / "tracker"


def tracker_cli() -> Any:

    name = "basicly_tracker_kit_cli"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    source = TRACKER_DIR / "cli.py"
    spec = importlib.util.spec_from_file_location(name, source)
    if not source.is_file() or spec is None or spec.loader is None:
        raise SystemExit(
            f"the board kit needs the tracker kit beside it at {TRACKER_DIR}; "
            f"install it with `basicly-tracker init`"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_SHAPE = {"title": "--title", "description": "--description"}
_SHAPE.update(acceptance="--acceptance", requirements="--requirements")
_CREATE_KEYS = frozenset({*_SHAPE, "fields", "parent", "prefix"})
_UPDATE_KEYS = frozenset({*_SHAPE, "fields", "status", "add_labels", "remove_labels", "if_seq"})


class RequestError(ValueError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def refuse(message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> RequestError:
    return RequestError(status, message)


def _record(value: str) -> str:
    if not tracker_cli().ids.is_record_id(value):
        raise refuse(f"{value!r} is not a record id")
    return value


def _query(query: dict, name: str, flag: str) -> list:
    values = query.get(name)
    return [f"{flag}={values[0]}"] if values else []


def _text(body: dict, key: str) -> str:
    value = body.get(key, "")
    if not isinstance(value, str):
        raise refuse(f"{key} must be a string")
    return value


def _checked(body: object, allowed: frozenset) -> dict:
    if not isinstance(body, dict):
        raise refuse("the body must be one JSON object")
    if unknown := sorted(set(body) - allowed):
        raise refuse(f"unknown key(s) {unknown}; allowed: {sorted(allowed)}")
    return body


def _named(body: dict) -> dict:
    named = body.get("fields", {})
    if not isinstance(named, dict):
        raise refuse("fields must map a field name to its value")
    return named


def _shape_options(body: dict) -> list:

    options = [f"{flag}={_text(body, key)}" for key, flag in _SHAPE.items() if key in body]
    options += [
        f"--field={name}={json.dumps(value)}" for name, value in sorted(_named(body).items())
    ]
    return options


def _seq(body: dict) -> int:
    value = body.get("if_seq")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise refuse("if_seq must be the record's seq as a whole number")
    return value


def _labels(body: dict, key: str, flag: str) -> list:
    values = body.get(key, [])
    if not isinstance(values, list) or not all(isinstance(one, str) for one in values):
        raise refuse(f"{key} must be a list of label strings")
    return [f"{flag}={one}" for one in values]


def default_prefix(ledger: Path) -> str:

    cli = tracker_cli()
    ids = cli.ids
    roots = Counter(
        record.partition(ids.PREFIX_SEP)[0]
        for record in cli.queries.folded(ledger)
        if ids.CHILD_SEP not in record
    )
    if len(roots) != 1:
        raise refuse(
            f"name the id prefix as prefix: this ledger holds {len(roots)} root prefixes "
            f"({', '.join(sorted(roots)) or 'none'}), so none is the obvious one"
        )
    return next(iter(roots))


def read_argv(ledger: Path, path: str, query: dict) -> list:

    parts = [unquote(part) for part in path[len(API) :].strip("/").split("/") if part]
    where = str(ledger)
    if len(parts) == 1 and parts[0] in READS:
        limit = _query(query, "limit", "--limit") if parts[0] == "ready" else []
        kind = _query(query, "type", "--type") if parts[0] == "scaffold" else []
        return [parts[0], *limit, *kind, "--", where]
    if parts == ["records"]:
        filters = _query(query, "status", "--status") + _query(query, "limit", "--limit")
        return ["list", *filters, "--", where]
    if len(parts) == 2 and parts[0] == "records":
        return ["show", "--", where, _record(parts[1])]
    if len(parts) == 3 and parts[0] == "records" and parts[2] == "dor":
        return ["dor", "--", where, _record(parts[1])]
    raise refuse(f"no read at {path}; GET {API} lists them", HTTPStatus.NOT_FOUND)


def write_argv(ledger: Path, method: str, path: str, body: object) -> list:

    parts = [unquote(part) for part in path[len(API) :].strip("/").split("/") if part]
    where = str(ledger)
    if method == "POST" and parts == ["records"]:
        held = _checked(body, _CREATE_KEYS)
        options = _shape_options(held)
        parent = _text(held, "parent")
        if parent:
            return ["child", *options, "--", where, _record(parent)]
        prefix = _text(held, "prefix") or default_prefix(ledger)
        return ["create", f"--prefix={prefix}", *options, "--", where]
    if len(parts) < 2 or parts[0] != "records":
        raise refuse(f"no write at {path}; GET {API} lists them", HTTPStatus.NOT_FOUND)
    record = _record(parts[1])
    if method == "PATCH" and len(parts) == 2:
        held = dict(_checked(body, _UPDATE_KEYS))
        if "title" in held:
            held["fields"] = {**_named(held), "title": _text(held, "title")}
            del held["title"]
        options = _shape_options(held)
        options += [f"--status={_text(held, 'status')}"] if "status" in held else []
        options += [f"--if-seq={_seq(held)}"] if "if_seq" in held else []
        options += _labels(held, "add_labels", "--add-label")
        options += _labels(held, "remove_labels", "--remove-label")
        return ["update", *options, "--", where, record]
    action = parts[2] if len(parts) == 3 else ""
    build = _ACTIONS.get(action) if method == "POST" else None
    if build is None:
        raise refuse(f"no {method} at {path}; GET {API} lists them", HTTPStatus.NOT_FOUND)
    return build(where, record, body)


def _comment_argv(where: str, record: str, body: object) -> list:
    return ["comment", "--", where, record, _text(_checked(body, frozenset({"text"})), "text")]


def _close_argv(where: str, record: str, body: object) -> list:
    reason = _text(_checked(body, frozenset({"reason"})), "reason")
    return ["close", f"--reason={reason}", "--", where, record]


def _dep_argv(where: str, record: str, body: object) -> list:
    held = _checked(body, frozenset({"target", "type"}))
    kind = [f"--type={_text(held, 'type')}"] if "type" in held else []
    return ["dep", *kind, "--", where, record, _record(_text(held, "target"))]


def _undep_argv(where: str, record: str, body: object) -> list:
    return ["undep", *_dep_argv(where, record, body)[1:]]


def _hold_argv(action: str) -> Callable[[str, str, object], list]:

    def build(where: str, record: str, body: object) -> list:
        held = _checked(body, frozenset({"to", "take"}))
        options = [f"--to={_text(held, 'to')}"] if _text(held, "to") else []
        options += ["--take"] if held.get("take") is True else []
        return [action, *options, "--", where, record]

    return build


def _unassign_argv(where: str, record: str, body: object) -> list:
    _checked(body, frozenset())
    return ["unassign", "--", where, record]


_ACTIONS: dict[str, Callable[[str, str, object], list]] = {
    "comments": _comment_argv,
    "close": _close_argv,
    "deps": _dep_argv,
    "undep": _undep_argv,
    "assign": _hold_argv("assign"),
    "claim": _hold_argv("claim"),
    "unassign": _unassign_argv,
}
