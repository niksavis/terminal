from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside cli.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


snapshot = _load("snapshot.py", "basicly_tracker_kit_snapshot")
scheduler = _load("scheduler.py", "basicly_tracker_kit_scheduler")
commands = _load("commands.py", "basicly_tracker_kit_commands")
queries = _load("queries.py", "basicly_tracker_kit_queries")
fsck = _load("fsck.py", "basicly_tracker_kit_fsck")
migrate = _load("migrate.py", "basicly_tracker_kit_migrate")
shaping = _load("shaping.py", "basicly_tracker_kit_shaping")
record_view = _load("record_view.py", "basicly_tracker_kit_record_view")
board = _load("board.py", "basicly_tracker_kit_board")
fields = _load("fields.py", "basicly_tracker_kit_fields")
arguments = _load("arguments.py", "basicly_tracker_kit_arguments")
events = snapshot.events
ids = events.ids

EXIT_OK = 0

EXIT_REFUSED = 1

SCHEMA_PREFIX = "basicly.tracker"

_BLOCKING_REPORTS = frozenset({
    "create",
    "child",
    "update",
    "assign",
    "claim",
    "unassign",
    "resolve",
    "close",
    "comment",
    "dep",
    "delete",
    "dor",
})

_STARTS_A_LEDGER = frozenset({"create", "import"})


def _field_value(raw: str) -> object:

    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _fields(
    title: str, pairs: Sequence[str], shape: argparse.Namespace | None = None
) -> dict[str, object]:

    fields: dict[str, object] = {}
    if title:
        fields[scheduler.TITLE_FIELD] = title
    fields.update(_shape_fields(shape))
    for pair in pairs:
        name, sep, raw = pair.partition("=")
        if not sep or not name:
            raise ValueError(f"--field {pair!r} is not name=value")
        fields[name] = _field_value(raw)
    return fields


def _shape_fields(shape: argparse.Namespace | None):

    if shape is None:
        return ()
    declared = (
        (shaping.ACCEPTANCE_FIELD, getattr(shape, "acceptance", None)),
        (shaping.REQUIREMENTS_FIELD, getattr(shape, "requirements", None)),
        (shaping.DESCRIPTION_FIELD, getattr(shape, "description", None)),
    )
    return tuple((name, value) for name, value in declared if value)


def _minting(fields: dict[str, object]) -> dict[str, object]:
    fields.setdefault(shaping.SHAPED_UNDER_FIELD, shaping.SHAPING_RULE)
    return fields


create_record = commands.create_root
query_records = queries.query_records
read_record = record_view.read_record
_owed_of = record_view.owed_of


_WRITES: dict[str, Callable[[argparse.Namespace, Any], Sequence[Any]]] = {
    "child": lambda a, r: commands.create_child(
        a.directory,
        a.parent,
        _minting(_fields(a.title, a.field, a)),
        status=a.status,
        redact=r,
    ),
    "update": lambda a, r: commands.update(
        a.directory,
        a.record,
        fields=_fields("", a.field, a),
        status=a.status,
        add_labels=a.add_label,
        remove_labels=a.remove_label,
        redact=r,
    ),
    "close": lambda a, r: commands.close(a.directory, a.record, reason=a.reason, redact=r),
    "comment": lambda a, r: commands.comment(a.directory, a.record, a.text, redact=r),
    "dep": lambda a, r: commands.add_dependency(
        a.directory, a.record, a.target, edge_type=a.edge_type, redact=r
    ),
    "delete": lambda a, r: commands.delete(a.directory, a.record, redact=r),
    "assign": lambda a, r: commands.assign(
        a.directory, a.record, _holder(a), take=a.take, redact=r
    ),
    "claim": lambda a, r: commands.claim(a.directory, a.record, _holder(a), take=a.take, redact=r),
    "unassign": lambda a, r: commands.unassign(a.directory, a.record, redact=r),
    "resolve": lambda a, r: commands.resolve(a.directory, a.record, redact=r),
}


def _holder(args: argparse.Namespace) -> str:
    return getattr(args, "to", "") or commands.holders.default_holder(Path.cwd())


def _compacted(args: argparse.Namespace) -> dict[str, object]:
    done = snapshot.compact(args.directory, writers=tuple(args.writer))
    return {
        "trunk": done.trunk.name,
        "shards": [path.name for path in done.shards],
        "appended": done.appended,
        "duplicates": done.duplicates,
    }


_VIEWS: dict[
    str, Callable[[argparse.Namespace, Callable[[str], str] | None], dict[str, object]]
] = {
    "ready": lambda a, _r: queries.ready(
        a.directory, limit=a.limit, mine=_holder(a) if a.mine else ""
    ),
    "blocked": lambda a, _r: queries.blocked(a.directory),
    "stats": lambda a, _r: queries.stats(a.directory),
    "compact": lambda a, _r: _compacted(a),
    "shards": lambda a, _r: fsck.shards_report(a.directory),
    "board": lambda a, _r: {"written": board.write(a.directory, a.out).as_posix()},
    "import": lambda a, r: migrate.import_report(
        a.directory, a.export, source=a.source, redact=r, dry_run=a.dry_run
    ),
    "scaffold": lambda a, _r: record_view.scaffold_of(a.directory, a.type),
    "fields": lambda a, _r: fields.table(record_view.templates.load(a.directory)),
    "refine": lambda a, _r: record_view.refine_queue(a.directory),
    "migrate-fields": lambda a, r: {
        "appended": [event.record for event in commands.migrate_fields(a.directory, redact=r)]
    },
}


def _shown(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    found = read_record(args.directory, args.record)
    if found is None:
        return EXIT_REFUSED, {"record": args.record, "found": False}
    return EXIT_OK, found


def _dor(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    verdict = _owed_of(args.directory, args.record)
    ready = not verdict["blocking"]
    return (EXIT_OK if ready else EXIT_REFUSED), {
        "record": args.record,
        "ready": ready,
        **verdict,
    }


def _fsck(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    rebuilt: dict[str, object] = {}
    if args.rebuild:
        done = fsck.rebuild(args.directory)
        rebuilt = {
            "rebuilt": [path.name for path in done.written],
            "removed": [path.name for path in done.removed],
        }
    report = fsck.check(args.directory)
    return (EXIT_OK if report.clean else report.exit_code), {**report.as_dict(), **rebuilt}


_REFUSABLE: dict[str, Callable[[argparse.Namespace], tuple[int, dict[str, object]]]] = {
    "show": _shown,
    "dor": _dor,
    "fsck": _fsck,
}


def _run(
    args: argparse.Namespace, redact: Callable[[str], str] | None
) -> tuple[int, dict[str, object]]:
    starts = args.command in _STARTS_A_LEDGER and not getattr(args, "dry_run", False)
    args.directory = commands.resolve_ledger(args.directory, starts=starts)
    if args.command == "create":
        written = create_record(
            args.directory,
            _minting(_fields(args.title, args.field, args)),
            prefix=args.prefix,
            status=args.status,
            redact=redact,
        )
        record = written[0].record
        return EXIT_OK, {
            "record": record,
            "events": [event.id for event in written],
            **_owed_of(args.directory, record),
        }
    if (gate := _REFUSABLE.get(args.command)) is not None:
        return gate(args)
    if (view := _VIEWS.get(args.command)) is not None:
        return EXIT_OK, view(args, redact)
    if (write := _WRITES.get(args.command)) is not None:
        appended = write(args, redact)
        if appended:
            record = appended[0].record
        else:
            ids = args.record
            record = ids if isinstance(ids, str) else ids[0]
        return EXIT_OK, {
            "record": record,
            "events": [event.id for event in appended],
            "appended": bool(appended),
            **_owed_of(args.directory, record),
        }
    records = query_records(args.directory, status=args.status, limit=args.limit)
    return EXIT_OK, {"count": len(records), "records": records}


def invoke(args: argparse.Namespace, redact: Callable[[str], str] | None = None) -> tuple:

    report: Mapping[str, object]
    try:
        code, report = _run(args, redact)
    except events.LedgerError as exc:
        code, report = EXIT_REFUSED, {"refused": str(exc)}
    except ValueError as exc:
        code, report = EXIT_REFUSED, {"refused": str(exc)}
    version = 2 if args.command in _BLOCKING_REPORTS else 1
    return code, {"schema": f"{SCHEMA_PREFIX}.{args.command}.v{version}", **report}


def main(argv: Sequence[str] | None = None, *, redact: Callable[[str], str] | None = None) -> int:

    args = arguments.parser().parse_args(argv)
    code, report = invoke(args, redact)
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
