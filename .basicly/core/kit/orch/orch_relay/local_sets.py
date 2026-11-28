from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

from orch_lessons.log import RefusedError


def _rule() -> ModuleType:
    try:
        return importlib.import_module("local_runs")
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))
        return importlib.import_module("local_runs")


def refuse(command: str, label: str) -> None:
    rule = _rule()
    for line in command.splitlines():
        found = rule.refusal(line)
        if found:
            raise RefusedError(
                f"orch decide refuses {label}: it names a local test set ({found}); "
                f"a decision never orders one: {rule.ALLOWED}"
            )
