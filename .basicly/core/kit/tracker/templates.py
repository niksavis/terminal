from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

TEMPLATE_FILE = "template.json"
SCHEMA = "basicly.tracker.template.v1"
EXTEND = "extend"
OVERRIDE = "override"
_KEYS = frozenset({"schema", "mode", "sections", "types", "stale_days", "prefix"})
DEFAULT_STALE_DAYS = 14


class TemplateError(ValueError):
    pass


class Template(NamedTuple):
    mode: str = EXTEND
    sections: tuple = ()
    types: tuple = ()
    stale_days: int = DEFAULT_STALE_DAYS
    prefix: str = ""

    @property
    def extends(self) -> bool:
        return self.mode == EXTEND

    def for_type(self, kind: str) -> tuple:
        return dict(self.types).get(kind, ())


DEFAULT = Template()


def _headings(value: object, where: str) -> tuple:

    if not isinstance(value, list) or not all(
        isinstance(one, str) and one.startswith("## ") and one[3:].strip() for one in value
    ):
        raise TemplateError(f"{where} must be a list of '## Heading' strings, not {value!r}")
    return tuple(one.strip() for one in value)


def read(directory: Path | str) -> dict:

    path = Path(directory) / TEMPLATE_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise TemplateError(f"{path} is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise TemplateError(f"{path} must hold one JSON object")
    return data


def load(directory: Path | str) -> Template:

    return parse(read(directory), Path(directory) / TEMPLATE_FILE)


def parse(data: dict, path: Path) -> Template:

    if unknown := sorted(set(data) - _KEYS):
        raise TemplateError(f"{path} names unknown key(s) {unknown}; allowed: {sorted(_KEYS)}")
    if data.get("schema", SCHEMA) != SCHEMA:
        raise TemplateError(f"{path} declares schema {data['schema']!r}; this kit reads {SCHEMA}")
    mode = data.get("mode", EXTEND)
    if mode not in (EXTEND, OVERRIDE):
        raise TemplateError(f"{path} mode must be {EXTEND!r} or {OVERRIDE!r}, not {mode!r}")
    types = data.get("types", {})
    if not isinstance(types, dict):
        raise TemplateError(f"{path} types must map a record type to its headings")
    stale_days = data.get("stale_days", DEFAULT_STALE_DAYS)
    if isinstance(stale_days, bool) or not isinstance(stale_days, int) or stale_days < 1:
        raise TemplateError(f"{path} stale_days must be a whole number of days, 1 or more")
    prefix = data.get("prefix", "")
    if not isinstance(prefix, str):
        raise TemplateError(f"{path} prefix must be a string, not {prefix!r}")
    return Template(
        mode,
        _headings(data.get("sections", []), f"{path} sections"),
        tuple(
            sorted((name, _headings(one, f"{path} types.{name}")) for name, one in types.items())
        ),
        stale_days,
        prefix,
    )
