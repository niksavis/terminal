from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside refine_sheet.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


record_view = _load("record_view.py", "basicly_tracker_kit_record_view")
commands = _load("commands.py", "basicly_tracker_kit_commands")
vault_migration_cli = _load("vault_migration_cli.py", "basicly_tracker_kit_vault_migration_cli")
shaping = record_view.shaping

SMALL_TYPES = ("task", "bug", "chore")
ACCEPTANCE = "acceptance:"
CONTEXT = "context:"
TITLE = "title:"
SHEETABLE = frozenset({shaping.ACCEPTANCE_HEADING, shaping.CONTEXT_HEADING})


def add_parsers(sub: Any) -> None:
    vault_migration_cli.add_parser(sub)
    sheet = sub.add_parser("refine-sheet", help="write a sheet of the records that miss criteria")
    sheet.add_argument("directory", help="the ledger directory")
    sheet.add_argument("--out", default="", help="the sheet file; default: inside the git folder")
    applied = sub.add_parser("apply-sheet", help="apply a filled refine sheet")
    applied.add_argument("directory", help="the ledger directory")
    applied.add_argument(
        "sheet", nargs="?", default="", help="the filled sheet; default: as written"
    )


def _owing(directory: Path | str) -> list[dict[str, object]]:
    queue = record_view.refine_queue(directory)["records"]
    return [row for row in queue if SHEETABLE & set(row["blocking"])]


SHEET_NAME = "basicly-refine-sheet.txt"


def sheet_path(directory: Path | str, given: str) -> Path:
    if given:
        return Path(given)
    root = Path(directory).resolve()
    for folder in (root, *root.parents):
        found = commands.git_layout.git_dir(folder)
        if found is not None:
            return found / SHEET_NAME
    return root.parent / SHEET_NAME


def write(directory: Path | str, out: Path) -> dict[str, object]:
    if out.exists():
        raise ValueError(f"{out} exists; name a new sheet file")
    states = record_view.queries.folded(directory)
    rows = _owing(directory)
    if not rows:
        return {"written": "", "records": [], "next": "ready"}
    blocks = []
    for row in rows:
        fields = states[str(row["record"])].fields
        context = shaping.section_text(
            str(fields.get("description") or ""), shaping.CONTEXT_HEADING
        )
        head = f"## {row['record']}\n{TITLE} {row['title']}\n{CONTEXT} {context.strip()}"
        blocks.append(f"{head}\n{ACCEPTANCE}\n{_criteria_lines(fields)}\n")
    out.write_text("\n".join(blocks), encoding="utf-8")
    return {
        "written": out.as_posix(),
        "records": [row["record"] for row in rows],
        "next": f"fill each acceptance line in {out.as_posix()}, then: apply-sheet {directory}",
    }


def _criteria_lines(fields: Mapping[str, object]) -> str:
    stated = str(fields.get("acceptance_criteria") or "")
    lines = [line.strip().removeprefix("- ").strip() for line in stated.splitlines()]
    return "\n".join(f"- {line}" for line in lines if line) or "- "


def parse(text: str) -> dict[str, dict[str, object]]:
    sheet: dict[str, dict[str, object]] = {}
    current: dict[str, object] | None = None
    in_acceptance = False
    for line in text.splitlines():
        if line.startswith("## "):
            current = {"context": "", "acceptance": []}
            sheet[line[3:].strip()] = current
            in_acceptance = False
        elif current is None:
            continue
        elif line.startswith(CONTEXT):
            current["context"] = line[len(CONTEXT) :].strip()
        elif line.startswith(ACCEPTANCE):
            in_acceptance = True
        elif in_acceptance:
            criterion = line.strip().removeprefix("- ").strip()
            if criterion and criterion != "-":
                acceptance = current["acceptance"]
                assert isinstance(acceptance, list)
                acceptance.append(criterion)
    return sheet


def _updates(fields: Mapping[str, object], entry: Mapping[str, object]) -> dict[str, object]:
    criteria = list(entry["acceptance"]) if isinstance(entry["acceptance"], list) else []
    updates: dict[str, object] = {"acceptance_criteria": "\n".join(f"- {one}" for one in criteria)}
    described = str(fields.get("description") or "")
    if entry["context"] and not shaping.section_text(described, shaping.CONTEXT_HEADING).strip():
        kept = [line for line in described.splitlines() if line.strip() != shaping.CONTEXT_HEADING]
        rest = "\n".join(kept).strip()
        context = f"{shaping.CONTEXT_HEADING}\n{entry['context']}"
        updates["description"] = f"{context}\n\n{rest}" if rest else context
    if fields.get("issue_type") in SMALL_TYPES and len(criteria) == 1:
        updates["size"] = "small"
    return updates


def apply(
    directory: Path | str, sheet: Path, *, context: Any = None, view: Any = None
) -> dict[str, object]:
    seen = view or (lambda: directory)
    if not sheet.is_file():
        raise ValueError(f"no sheet at {sheet}; write one with refine-sheet LEDGER --out {sheet}")
    entries = parse(sheet.read_text(encoding="utf-8"))
    if not entries:
        raise ValueError(
            f"{sheet} names no record; delete it, then write one with refine-sheet {directory}"
        )
    states = record_view.queries.folded(seen())
    unknown = sorted(record for record in entries if record not in states)
    empty = sorted(record for record, entry in entries.items() if not entry["acceptance"])
    if unknown or empty:
        named = [*(f"{record} is not in the ledger" for record in unknown)]
        named += [f"{record} has an empty acceptance line" for record in empty]
        raise ValueError(f"nothing was applied: {'; '.join(named)}; fill the sheet and apply again")
    for record, entry in sorted(entries.items()):
        commands.update(
            directory, record, fields=_updates(states[record].fields, entry), context=context
        )
    left = {
        str(row["record"]): row["blocking"] for row in record_view.refine_queue(seen())["records"]
    }
    sheet.unlink()
    ranked = {str(row["record"]) for row in record_view.queries.ready(seen())["records"]}
    return {
        "applied": sorted(entries),
        "shaped": sorted(record for record in entries if record not in left),
        "ready": sorted(record for record in entries if record in ranked),
        "still_owed": {record: left[record] for record in sorted(entries) if record in left},
    }
