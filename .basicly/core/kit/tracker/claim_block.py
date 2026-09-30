from __future__ import annotations

import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

CLAIM_BEGIN = "# >>> basicly-tracker claim >>>"
CLAIM_END = "# <<< basicly-tracker claim <<<"
CLI_FILE = "cli.py"
INSTALLED_SKILLS = ("tracker", "board")
INSTALLED_FILES = (".gitignore", ".gitattributes")

_HERE = Path(__file__).resolve().parent


def _locate() -> Any:

    cached = sys.modules.get("basicly_tracker_kit_locate")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location("basicly_tracker_kit_locate", _HERE / "locate.py")
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's locate.py is missing from beside claim_block.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["basicly_tracker_kit_locate"] = module
    spec.loader.exec_module(module)
    return module


def default_places(root: Path, kit: Path) -> list[str]:

    try:
        return [(kit / CLI_FILE).resolve().relative_to(Path(root).resolve()).as_posix()]
    except ValueError:
        return []


def default_managed(places: Sequence[str]) -> list[str]:

    return [f"{Path(place).parent.parent.as_posix()}/" for place in places]


def claim_body(ledger: str, places: Sequence[str], managed: Sequence[str]) -> str:
    locate = _locate()
    installed = [*managed, *INSTALLED_FILES]
    for agents in (".claude", ".agents"):
        installed += [f"{agents}/skills/{name}/" for name in INSTALLED_SKILLS]
    flags = " ".join(f'--installed "{one}"' for one in installed)
    check = f'"$@" commit-check "{ledger}" "$tracker_message" --stdin --runner "$tracker_typed"'
    return "\n".join((
        CLAIM_BEGIN,
        f'if [ -d "{ledger}" ] && ! git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then',
        '  tracker_message="$1"',
        f"  tracker_check() {{ git diff --cached --name-only | {check} {flags}; }}",
        *locate.shell_lines(ledger, places),
        '  tracker_python=""',
        "  for tracker_try in python3 python; do",
        '    command -v "$tracker_try" >/dev/null 2>&1 || continue',
        '    tracker_python="$tracker_try"',
        "    break",
        "  done",
        '  if [ -n "$tracker_file" ] && [ -n "$tracker_python" ]; then',
        '    tracker_typed="python3 $tracker_file"',
        '    tracker_out=$(tracker_check "$tracker_python" "$tracker_file") ||',
        '      { echo "$tracker_out" >&2; exit 1; }',
        f'  elif [ -z "$tracker_file" ] && command -v {locate.COMMAND} >/dev/null 2>&1; then',
        f'    tracker_typed="{locate.COMMAND}"',
        f"    tracker_out=$(tracker_check {locate.COMMAND}) ||",
        '      { echo "$tracker_out" >&2; exit 1; }',
        "  else",
        '    echo "$tracker_missing" >&2',
        "    exit 1",
        "  fi",
        "fi",
        CLAIM_END,
    ))
