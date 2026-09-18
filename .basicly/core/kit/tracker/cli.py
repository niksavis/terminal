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
events = snapshot.events
ids = events.ids

DEFAULT_STATUS = "open"

EXIT_OK = 0

EXIT_REFUSED = 1


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


def _add_shape_arguments(parser: Any) -> None:
    parser.add_argument(
        "--acceptance",
        default="",
        metavar="TEXT",
        help="the acceptance criteria a check is derived from",
    )
    parser.add_argument(
        "--requirements",
        default="",
        metavar="TEXT",
        help="the requirements validation judges the built thing against",
    )
    parser.add_argument(
        "--description",
        default="",
        metavar="TEXT",
        help="the record's body, which may carry the sections as headings instead",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, read, query and advance work items in a tracker kit ledger."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="mint a record id and append its first events")
    create.add_argument("directory", help=f"the ledger directory holding {events.LOG_GLOB}")
    create.add_argument("--prefix", required=True, help="the ledger's id prefix, e.g. acme")
    create.add_argument("--title", default="", help="the record's title")
    create.add_argument(
        "--field",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="an extra field; the value is read as JSON when it parses, else as a string",
    )
    create.add_argument("--status", default=DEFAULT_STATUS, help="the status to open it at")
    _add_shape_arguments(create)

    show = sub.add_parser("show", help="read one record's folded state and both edge directions")
    show.add_argument("directory", help="the ledger directory")
    show.add_argument("record", help="the record id")

    listing = sub.add_parser("list", help="query the records the ledger holds")
    listing.add_argument("directory", help="the ledger directory")
    listing.add_argument("--status", default=None, help="only records at this status")
    listing.add_argument("--limit", type=int, default=None, help="at most this many records")

    compaction = sub.add_parser(
        "compact", help="fold every pending writer shard into the trunk log and unlink it"
    )
    compaction.add_argument("directory", help="the ledger directory")
    compaction.add_argument(
        "--writer",
        action="append",
        default=[],
        metavar="WRITER",
        help="only this writer's shard; repeats. Every shard when omitted",
    )

    shards = sub.add_parser("shards", help="the pending writer shards this ledger holds")
    shards.add_argument("directory", help="the ledger directory")

    page = sub.add_parser("board", help="write one self-contained HTML page a human can open")
    page.add_argument("directory", help="the ledger directory")
    page.add_argument("--out", default="tracker-board.html", help="the file to write")

    check = sub.add_parser(
        "fsck", help="fold the whole log and report anything unparseable or broken"
    )
    check.add_argument("directory", help="the ledger directory")
    check.add_argument(
        "--rebuild",
        action="store_true",
        help="delete every derived file and write it again from the log before checking",
    )

    gate = sub.add_parser(
        "dor",
        help="the definition of ready: refuse a record that cannot be verified against",
    )
    gate.add_argument("directory", help="the ledger directory")
    gate.add_argument("record", help="the record id")

    bring = sub.add_parser(
        "import", help="import a foreign tracker's JSONL export into this ledger"
    )
    bring.add_argument("directory", help="the ledger directory")
    bring.add_argument("export", help="the export file to read, one JSON record per line")
    bring.add_argument(
        "--source",
        default="",
        help="the name recorded as the provenance of every imported record; "
        "defaults to the export's file name",
    )
    bring.add_argument(
        "--dry-run",
        action="store_true",
        help="report what the same plan would write, and write nothing",
    )

    _add_query_parsers(sub)
    _add_write_parsers(sub)
    return parser


def _add_query_parsers(sub: Any) -> None:
    for name, helping in (
        ("ready", "the ranked ready set: what can be worked on now"),
        ("blocked", "each dispatchable record that is not ready, and what holds it"),
        ("stats", "counts by status, plus the ready and blocked counts"),
    ):
        view = sub.add_parser(name, help=helping)
        view.add_argument("directory", help="the ledger directory")
        if name == "ready":
            view.add_argument("--limit", type=int, default=None, help="at most this many")


def _add_write_parsers(sub: Any) -> None:
    child = sub.add_parser("child", help="mint the next child id under a parent")
    child.add_argument("directory", help="the ledger directory")
    child.add_argument("parent", help="the parent record id")
    child.add_argument("--title", default="", help="the record's title")
    child.add_argument("--field", action="append", default=[], metavar="NAME=VALUE")
    child.add_argument("--status", default=DEFAULT_STATUS, help="the status to open it at")
    _add_shape_arguments(child)

    update = sub.add_parser("update", help="set a record's fields, status or labels")
    update.add_argument("directory", help="the ledger directory")
    update.add_argument("record", help="the record id")
    update.add_argument("--field", action="append", default=[], metavar="NAME=VALUE")
    update.add_argument("--status", default="", help="the status to move it to")
    update.add_argument("--add-label", action="append", default=[], metavar="LABEL")
    update.add_argument("--remove-label", action="append", default=[], metavar="LABEL")
    _add_shape_arguments(update)

    closing = sub.add_parser("close", help="move records to the closed status")
    closing.add_argument("directory", help="the ledger directory")
    closing.add_argument("record", nargs="+", help="the record ids to close")
    closing.add_argument("--reason", default="", help="why, recorded as a field")

    note = sub.add_parser("comment", help="append one comment to a record")
    note.add_argument("directory", help="the ledger directory")
    note.add_argument("record", help="the record id")
    note.add_argument("text", help="the comment body")

    dep = sub.add_parser("dep", help="record a dependency edge on the dependent")
    dep.add_argument("directory", help="the ledger directory")
    dep.add_argument("record", help="the dependent record id")
    dep.add_argument("target", help="the record it depends on")
    dep.add_argument("--type", dest="edge_type", default="blocks", help="the edge type")

    removal = sub.add_parser("delete", help="tombstone a record; its id is never reused")
    removal.add_argument("directory", help="the ledger directory")
    removal.add_argument("record", help="the record id")


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
}


def _compacted(args: argparse.Namespace) -> dict[str, object]:
    done = snapshot.compact(args.directory, writers=tuple(args.writer))
    return {
        "trunk": done.trunk.name,
        "shards": [path.name for path in done.shards],
        "appended": done.appended,
        "duplicates": done.duplicates,
    }


def _imported(args: argparse.Namespace, redact: Callable[[str], str] | None) -> dict[str, object]:
    source = args.source or Path(args.export).name
    read = migrate.read_snapshot(args.export, name=source)
    report = migrate.import_snapshot(args.directory, read, redact=redact, dry_run=args.dry_run)
    return {
        "source": source,
        "dry_run": args.dry_run,
        "imported": report.imported,
        "diverged": report.diverged,
        "absent": report.absent,
        "tombstoned": report.tombstoned,
        "rejected": [
            {"subject": one.subject, "reason": one.reason}
            for one in (*report.rejected, *report.unreadable)
        ],
    }


def _shards(args: argparse.Namespace) -> dict[str, object]:
    held = events.pending_paths(args.directory)
    return {
        "count": len(held),
        "writers": [events.writer_of(path) for path in held],
        "warn_above": fsck.SHARDS_WARN_ABOVE,
        "refuse_above": fsck.SHARDS_REFUSE_ABOVE,
    }


_VIEWS: dict[
    str, Callable[[argparse.Namespace, Callable[[str], str] | None], dict[str, object]]
] = {
    "ready": lambda a, _r: queries.ready(a.directory, limit=a.limit),
    "blocked": lambda a, _r: queries.blocked(a.directory),
    "stats": lambda a, _r: queries.stats(a.directory),
    "compact": lambda a, _r: _compacted(a),
    "shards": lambda a, _r: _shards(a),
    "board": lambda a, _r: {"written": board.write(a.directory, a.out).as_posix()},
    "import": _imported,
}


def _shown(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    found = read_record(args.directory, args.record)
    if found is None:
        return EXIT_REFUSED, {"record": args.record, "found": False}
    return EXIT_OK, found


def _dor(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    verdict = _owed_of(args.directory, args.record)
    ready = not verdict["refused"]
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


def main(argv: Sequence[str] | None = None, *, redact: Callable[[str], str] | None = None) -> int:

    args = _parser().parse_args(argv)
    report: Mapping[str, object]
    try:
        code, report = _run(args, redact)
    except events.LedgerError as exc:
        code, report = EXIT_REFUSED, {"refused": str(exc)}
    except ValueError as exc:
        code, report = EXIT_REFUSED, {"refused": str(exc)}
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
