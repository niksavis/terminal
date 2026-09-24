from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, NamedTuple

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside fields.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


shaping = _load("shaping.py", "basicly_tracker_kit_shaping")

REQUIRED = "required"
READY = "ready"
CLOSING = "closing"
OPTIONAL = "optional"
WRITER = "writer"
TEMPLATE = "template"
IMPORTED = "imported"
DERIVED = "derived"

WRITABLE_ROLES = frozenset({REQUIRED, READY, CLOSING, OPTIONAL, WRITER, TEMPLATE})

DATES_KEY = "dates"


class Field(NamedTuple):
    name: str
    role: str
    reader: str
    remedy: str = ""


TABLE = (
    Field("title", REQUIRED, "the ready list, the board and every record view"),
    Field("description", REQUIRED, "the trigger check of the definition of ready, and a brief"),
    Field("issue_type", REQUIRED, "the scaffold, the template types and the loop classification"),
    Field("priority", REQUIRED, "the ready ranking"),
    Field("acceptance_criteria", READY, "the definition of ready, and the check at verify"),
    Field("requirements", READY, "the definition of ready, and the judgement at validate"),
    Field("close_reason", CLOSING, "the close refusal; it is the permanent record of what shipped"),
    Field("labels", OPTIONAL, "label queries and the label shape check"),
    Field("assignee", OPTIONAL, "a person who asks who holds the record"),
    Field("external_ref", OPTIONAL, "the engine, which binds a record to its worktree"),
    Field("provenance", WRITER, "the importer and the fold; the writer sets it"),
    Field("shaped_under", WRITER, "the definition of ready; create sets it"),
    Field("import_digest", IMPORTED, "the importer, which skips a record it already holds"),
    Field("imported_from", IMPORTED, "the importer and the derived dates"),
    Field("created_at", IMPORTED, "the derived created date of an imported record"),
    Field("updated_at", IMPORTED, "the derived updated date of an imported record"),
    Field("closed_at", IMPORTED, "the derived closed date of an imported record"),
    Field("created_by", IMPORTED, "none; import history only", "the actor on each event says who"),
    Field("compaction_level", IMPORTED, "none; import history only"),
    Field("original_size", IMPORTED, "none; import history only"),
    Field("source_repo", IMPORTED, "none; import history only"),
    Field("source_repo_path", IMPORTED, "none; import history only"),
    Field("design", IMPORTED, "none; import history only", "put the design in the description"),
    Field("notes", IMPORTED, "none; import history only", "add a comment instead"),
    Field("owner", IMPORTED, "none; import history only", "set assignee instead"),
    Field(f"{DATES_KEY}.created", DERIVED, "every record view; the first event time"),
    Field(f"{DATES_KEY}.updated", DERIVED, "every record view; the last event time"),
    Field(f"{DATES_KEY}.closed", DERIVED, "every record view; the time of the closing status"),
)

BY_NAME = {field.name: field for field in TABLE}


class RefusedFieldError(ValueError):
    pass


def declared_by(template: Any) -> frozenset:

    if template is None:
        return frozenset()
    headings = [*template.sections, *(one for _kind, many in template.types for one in many)]
    return frozenset(shaping.field_of(heading) for heading in headings)


def refuse(name: str, template: Any = None) -> None:

    if name in declared_by(template):
        return
    known = BY_NAME.get(f"{DATES_KEY}.created" if name == DATES_KEY else name)
    if known is not None and known.role in WRITABLE_ROLES:
        return
    if known is None:
        callers = (one.name for one in TABLE if one.role in WRITABLE_ROLES - {WRITER})
        message = (
            f"field {name!r} is not in the field table, so nothing reads it; declare it as "
            f"a section in template.json, or write one of: {', '.join(callers)}"
        )
    elif known.role == DERIVED:
        message = f"{name!r} is computed from the event times; read it from `show`"
    else:
        message = f"field {name!r} is import history, which only `import` writes"
        message += f"; {known.remedy}" if known.remedy else ""
    raise RefusedFieldError(f"{message}. `fields` prints the table")


def table(template: Any = None) -> dict[str, object]:

    rows = [{"name": field.name, "role": field.role, "reader": field.reader} for field in TABLE]
    rows += [
        {"name": name, "role": TEMPLATE, "reader": "the definition of ready, as a template section"}
        for name in sorted(declared_by(template) - set(BY_NAME))
    ]
    return {"fields": rows}
