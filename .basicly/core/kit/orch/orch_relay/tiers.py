from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from orch_lessons.log import RefusedError

FILE = "tiers.json"
DEFAULT: dict[str, dict[str, str]] = {
    "cheap": {"claude": "haiku", "codex": "gpt-6-luna", "copilot": "mai-code-2-flash"},
}


def _seed(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(DEFAULT, out, indent=2, sort_keys=True)
    Path(name).replace(path)


def load(base: Path) -> dict[str, dict[str, str]]:
    path = base / FILE
    if not path.exists():
        _seed(path)
        return DEFAULT
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RefusedError(f"the tier map {path} is not readable JSON; fix or delete it") from error
    shaped = isinstance(value, dict) and all(
        isinstance(models, dict) and all(isinstance(m, str) for m in models.values())
        for models in value.values()
    )
    if not shaped:
        raise RefusedError(
            f"the tier map {path} must map each tier to an object of coding agent to model id"
        )
    return value


def model(base: Path, tier: str, vendor: str) -> str:
    known = load(base)
    if tier not in known:
        raise RefusedError(
            f"--tier {tier!r} is not in the tier map {base / FILE}; use one of: "
            f"{', '.join(sorted(known))}"
        )
    if vendor not in known[tier]:
        raise RefusedError(
            f"the tier {tier!r} in {base / FILE} names no model for the coding agent {vendor!r}; "
            f"add one there or pass --model"
        )
    return known[tier][vendor]
