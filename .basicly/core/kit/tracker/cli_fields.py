from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _shaping() -> Any:
    name = "basicly_tracker_kit_shaping"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name("shaping.py"))
    if spec is None or spec.loader is None:
        raise ImportError("shaping.py is missing from beside cli_fields.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


shaping = _shaping()


def field_value(raw: str) -> object:

    try:
        return json.loads(raw)
    except ValueError:
        return raw


def fields(
    title: str, pairs: Sequence[str], shape: argparse.Namespace | None = None
) -> dict[str, object]:

    fields: dict[str, object] = {}
    if title:
        fields["title"] = title
    fields.update(shape_fields(shape))
    for pair in pairs:
        name, sep, raw = pair.partition("=")
        if not sep or not name:
            raise ValueError(f"--field {pair!r} is not name=value")
        fields[name] = field_value(raw)
    return fields


def shape_fields(shape: argparse.Namespace | None) -> tuple[tuple[str, object], ...]:

    if shape is None:
        return ()
    declared = (
        (shaping.ACCEPTANCE_FIELD, getattr(shape, "acceptance", None)),
        (shaping.REQUIREMENTS_FIELD, getattr(shape, "requirements", None)),
        (shaping.DESCRIPTION_FIELD, getattr(shape, "description", None)),
    )
    return tuple((name, value) for name, value in declared if value)
