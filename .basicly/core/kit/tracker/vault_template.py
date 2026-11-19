from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    key = "basicly_tracker_kit_" + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, _HERE / (name + ".py"))
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's " + name + ".py is missing from beside it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


templates = _load("templates")
redact = _load("redact")
FIELD = "migration-template"
IDENTITY = "migration-template-id"


class VaultTemplateError(ValueError):
    pass


def identity(template: Mapping[str, object]) -> str:
    text = json.dumps(dict(template), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def prepare(raw: Mapping[str, object], redactor: Callable[[str], str] | None) -> dict[str, object]:
    templates.parse(dict(raw), Path(templates.TEMPLATE_FILE))

    def scrub(value: Any) -> Any:
        if isinstance(value, str):
            return redact.text(value if redactor is None else redactor(value))
        if isinstance(value, dict):
            return {scrub(key): scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    public = scrub(dict(raw))
    templates.parse(public, Path(templates.TEMPLATE_FILE))
    return public


def carried(lines: Sequence[Mapping[str, object]], prefix: str) -> dict[str, object] | None:
    required: set[str] = set()
    held: dict[str, dict[str, object]] = {}
    for line in lines:
        record = line.get("record")
        if not isinstance(record, str) or record.partition("-")[0] != prefix:
            continue
        if IDENTITY not in line and FIELD not in line:
            continue
        key = line.get(IDENTITY)
        if not isinstance(key, str):
            raise VaultTemplateError(
                "migration template identity is missing; repair the vault import"
            )
        required.add(key)
        if FIELD in line:
            value = line[FIELD]
            if (
                not isinstance(value, dict)
                or identity(value) != key
                or value.get("prefix") != prefix
            ):
                raise VaultTemplateError(
                    "migration template is malformed or altered; repair the vault import"
                )
            try:
                templates.parse(value, Path(templates.TEMPLATE_FILE))
            except templates.TemplateError:
                raise VaultTemplateError(
                    "migration template is invalid; repair the vault import"
                ) from None
            held[key] = value
    if len(required) > 1 or required - held.keys():
        raise VaultTemplateError(
            "migration template is missing or conflicting; repair the vault import"
        )
    return next(iter(held.values()), None)
