from __future__ import annotations

import importlib.util
import shutil
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

COMMAND = "basicly-tracker"
LATEST_SOURCE = "git+https://github.com/niksavis/basicly#subdirectory=packages/basicly-tracker"
MISSING = (
    "this repository holds a tracker ledger at {ledger}, and no tracker was found in "
    "{places} or as {command} on PATH, so the commit was refused. Install it with {install}"
)

_HERE = Path(__file__).resolve().parent


def _pin() -> Any:

    cached = sys.modules.get("basicly_tracker_kit_pin")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location("basicly_tracker_kit_pin", _HERE / "pin.py")
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's pin.py is missing from beside locate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["basicly_tracker_kit_pin"] = module
    spec.loader.exec_module(module)
    return module


class Tracker(NamedTuple):
    file: str
    command: str

    def argv(self, python: str) -> list[str]:
        return [python, self.file] if self.file else [self.command]

    def typed(self) -> str:
        return f"python3 {self.file}" if self.file else COMMAND


def locate(
    root: Path, places: Sequence[str], which: Callable[[str], str | None] = shutil.which
) -> Tracker | None:

    for relative in places:
        if (Path(root) / relative).is_file():
            return Tracker(relative, "")
    found = which(COMMAND)
    return Tracker("", found) if found else None


def install_command(version: str | None) -> str:

    source = _pin().INSTALL_SOURCE.format(version=version) if version else LATEST_SOURCE
    return f"uv tool install --force '{source}'"


def _message(ledger: str, places: Sequence[str], install: str) -> str:

    shown = ", ".join(places) or "no file"
    return MISSING.format(ledger=ledger, places=shown, command=COMMAND, install=install)


def missing(root: Path, ledger: str, places: Sequence[str]) -> str:

    version = _pin().pinned(Path(root) / ledger)
    return _message(ledger, places, f"`{install_command(version)}`")


def shell_lines(ledger: str, places: Sequence[str]) -> list[str]:

    tests = [f'[ -f "{relative}" ]; then tracker_file="{relative}"' for relative in places]
    chain = [f"  if {tests[0]}", *(f"  elif {test}" for test in tests[1:]), "  fi"] if tests else []
    pinned = _pin().INSTALL_SOURCE.format(version="$tracker_pin")
    return [
        '  tracker_file=""',
        *chain,
        f'  tracker_pin="$(cat "{ledger}/{_pin().PIN_FILE}" 2>/dev/null)"',
        f'  tracker_install="uv tool install --force {LATEST_SOURCE}"',
        f'  [ -z "$tracker_pin" ] || tracker_install="uv tool install --force {pinned}"',
        f'  tracker_missing="tracker-claim: {_message(ledger, places, "$tracker_install")}"',
    ]
