r"""The tracker kit's standalone entry point: the whole work graph from a command line.

The responsibility is *the command line*; the boundary is against the modules it drives.
Nothing here folds, mints or writes a line — ``events`` appends, ``ids`` mints,
``commands`` writes, ``queries`` reads.

**The gap it closes** (§4 in `SPEC.md`, a kit consumable with zero basicly imports
and nothing on PATH): the write side had only ``basicly tracker``, which is the engine, so
a repository that copied the kit could read a ledger it had no way to advance.

``create`` and ``child`` mint an id and open a record; ``show`` and ``list`` read;
``ready``, ``blocked`` and ``stats`` answer about the set; ``update``, ``close``,
``comment``, ``dep`` and ``delete`` advance one. ``fsck`` and ``snapshot`` keep their own
entry points, because each is a whole-ledger operation rather than a verb on a record.

**Redaction stays injected.** §4.2 requires a redaction pass on every write and the kit
may not import ``basicly.redact``, so :func:`main` takes the callable as a keyword. A bare
command line passes none and the ledger holds what the operator typed — honest for a typed
title, wrong for agent output, which belongs on the engine's write path.

Kit rules (`.basicly/core/kit/README.md`): no basicly, standard library only, no network,
no subprocess, and syntax an interpreter older than this repo's 3.14 floor can parse —
hence one exception class per handler.
"""

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
    """Load a sibling kit module by path, without touching ``sys.path``.

    The cache lookup is the point rather than the speed: a second load mints a second
    ``Event`` class, and a frozen dataclass compares unequal across the two. Every loader
    in the kit uses these same ``basicly_tracker_kit_<module>`` names for that reason.

    Raises:
        ImportError: *file_name* is not beside this file.
    """
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
events = snapshot.events
ids = events.ids

# The status a record is created with when the caller names none — the kit's own
# vocabulary spells it (`differential.Vocabulary.known_statuses`). Not validated against
# that set on the way in: the vocabulary is configurable because a consumer's statuses are
# its own, so refusing one here would refuse the case it exists for.
DEFAULT_STATUS = "open"

EXIT_OK = 0

# Every refusal: an unknown record, a directory that is not a ledger, a ledger that will
# not take the write. One code, because the report says which — a caller scripting this
# branches on the JSON, and a shell caller only needs "did it happen".
EXIT_REFUSED = 1


def _field_value(raw: str) -> object:
    """One ``--field`` value: JSON when it parses, otherwise the literal string.

    ``priority=2`` has to reach the ledger as an integer or ``scheduler._priority``
    silently reads it as the default band, and ``labels=["a"]`` as a list. Falling back to
    the string is what keeps ``title=fix the parser`` from needing quotes.
    """
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _fields(title: str, pairs: Sequence[str]) -> dict[str, object]:
    """The ``created`` event's payload, from ``--title`` and the ``--field name=value`` list.

    The title's field name comes from :data:`scheduler.TITLE_FIELD` rather than a literal:
    the store takes exactly one spelling per field, and the scheduler is the
    module that declares this one.

    Raises:
        ValueError: a pair has no ``=``.
    """
    fields: dict[str, object] = {}
    if title:
        fields[scheduler.TITLE_FIELD] = title
    for pair in pairs:
        name, sep, raw = pair.partition("=")
        if not sep or not name:
            raise ValueError(f"--field {pair!r} is not name=value")
        fields[name] = _field_value(raw)
    return fields


# The record operations, kept under their original names because this module is the
# kit's public entry point and `owned_write`, the engine and the kit's own tests reach
# them here. The bodies moved to the two modules whose boundary they belong to, which is
# the split this module's docstring already claimed; the read below composes two of
# those answers rather than folding a third.
create_record = commands.create_root
query_records = queries.query_records


def read_record(directory: Path | str, record: str) -> dict[str, object] | None:
    """One record's folded state with both directions of its dependency graph, or None.

    An edge is stored on the dependent, so a record's *dependents* are in no half of the
    fold and are inverted from the population; without them no kit command answered what
    a record holds up (basicly-ztik9a). Both keys are always present, because an absent
    one reads as a record with no edges. The engine renders the same two lists in
    `basicly.tracker._edges`, which the kit may not import — `test_tracker_query` holds
    the two producers to one shape.
    """
    states = queries.folded(directory)
    state = states.get(record)
    if state is None:
        return None
    views, _ = queries.views_and_children(directory)
    shown = snapshot.record_to_dict(state)
    shown.update(_edges(record, views, states))
    return shown


def _edges(record: str, views: Mapping[str, Any], states: Mapping[str, Any]) -> dict[str, object]:
    """*record*'s outgoing and incoming edges, each naming the other record's status.

    A target the fold does not hold is ``unknown``, the spelling `queries._open_blockers`
    uses: ``""`` is what a record that is held and never opened reads as.
    """
    view = views.get(record)
    return {
        "dependencies": [
            {
                "id": edge.target,
                "dependency_type": edge.type,
                "status": _status(views, edge.target),
            }
            for edge in (view.dependencies if view is not None else ())
        ],
        "dependents": [
            {
                "id": other,
                "dependency_type": edge.type,
                "status": held.status or "",
                "title": str(states[other].fields.get("title", "")) if other in states else "",
            }
            for other, held in sorted(views.items())
            for edge in held.dependencies
            if edge.target == record and not held.tombstoned
        ],
    }


def _status(views: Mapping[str, Any], record: str) -> str:
    """*record*'s status as the population reports it, or ``unknown`` when it holds none."""
    view = views.get(record)
    return "unknown" if view is None else view.status or ""


def _parser() -> argparse.ArgumentParser:
    """Every subcommand, each taking the ledger directory as its first argument."""
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

    show = sub.add_parser("show", help="read one record's folded state and both edge directions")
    show.add_argument("directory", help="the ledger directory")
    show.add_argument("record", help="the record id")

    listing = sub.add_parser("list", help="query the records the ledger holds")
    listing.add_argument("directory", help="the ledger directory")
    listing.add_argument("--status", default=None, help="only records at this status")
    listing.add_argument("--limit", type=int, default=None, help="at most this many records")

    _add_query_parsers(sub)
    _add_write_parsers(sub)
    return parser


def _add_query_parsers(sub: Any) -> None:
    """The three views a consumer needs to decide what to work on next."""
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
    """The writes that advance a record, as against the ``create`` that opens one."""
    child = sub.add_parser("child", help="mint the next child id under a parent")
    child.add_argument("directory", help="the ledger directory")
    child.add_argument("parent", help="the parent record id")
    child.add_argument("--title", default="", help="the record's title")
    child.add_argument("--field", action="append", default=[], metavar="NAME=VALUE")
    child.add_argument("--status", default=DEFAULT_STATUS, help="the status to open it at")

    update = sub.add_parser("update", help="set a record's fields, status or labels")
    update.add_argument("directory", help="the ledger directory")
    update.add_argument("record", help="the record id")
    update.add_argument("--field", action="append", default=[], metavar="NAME=VALUE")
    update.add_argument("--status", default="", help="the status to move it to")
    update.add_argument("--add-label", action="append", default=[], metavar="LABEL")
    update.add_argument("--remove-label", action="append", default=[], metavar="LABEL")

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


# Each write, as the call it makes. A dispatch table rather than a chain of comparisons,
# the same shape and the same reason as `mirror._MIRRORED_WRITES`: the write surface is
# what a reviewer checks against the tracker's documented verbs, and a branch buried in a
# function body is not readable as a set.
_WRITES: dict[str, Callable[[argparse.Namespace, Any], Sequence[Any]]] = {
    "child": lambda a, r: commands.create_child(
        a.directory, a.parent, _fields(a.title, a.field), status=a.status, redact=r
    ),
    "update": lambda a, r: commands.update(
        a.directory,
        a.record,
        fields=_fields("", a.field),
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

# Each read that answers about the set rather than about one record.
_VIEWS: dict[str, Callable[[argparse.Namespace], dict[str, object]]] = {
    "ready": lambda a: queries.ready(a.directory, limit=a.limit),
    "blocked": lambda a: queries.blocked(a.directory),
    "stats": lambda a: queries.stats(a.directory),
}


def _run(
    args: argparse.Namespace, redact: Callable[[str], str] | None
) -> tuple[int, dict[str, object]]:
    """Execute one parsed command, returning its exit code and the report to print."""
    if args.command == "create":
        written = create_record(
            args.directory,
            _fields(args.title, args.field),
            prefix=args.prefix,
            status=args.status,
            redact=redact,
        )
        return EXIT_OK, {"record": written[0].record, "events": [event.id for event in written]}
    if args.command == "show":
        found = read_record(args.directory, args.record)
        if found is None:
            return EXIT_REFUSED, {"record": args.record, "found": False}
        return EXIT_OK, found
    if (view := _VIEWS.get(args.command)) is not None:
        return EXIT_OK, view(args)
    if (write := _WRITES.get(args.command)) is not None:
        appended = write(args, redact)
        if appended:
            record = appended[0].record
        else:
            # `close` names ids (basicly-wu4w8v).
            ids = args.record
            record = ids if isinstance(ids, str) else ids[0]
        return EXIT_OK, {
            "record": record,
            "events": [event.id for event in appended],
            "appended": bool(appended),
        }
    records = query_records(args.directory, status=args.status, limit=args.limit)
    return EXIT_OK, {"count": len(records), "records": records}


def main(argv: Sequence[str] | None = None, *, redact: Callable[[str], str] | None = None) -> int:
    """Run one command and print its JSON report.

    Args:
        argv: The command line, defaulting to ``sys.argv[1:]``.
        redact: Applied to every string written, §4.2. Injected because the kit may not
            import the engine's redactor; a command line passes none.

    Returns:
        :data:`EXIT_OK`, or :data:`EXIT_REFUSED` with a ``refused`` or ``found: false``
        report. A refusal is printed rather than raised so the report is machine-readable
        on both paths.
    """
    args = _parser().parse_args(argv)
    report: Mapping[str, object]
    try:
        code, report = _run(args, redact)
    except events.LedgerError as exc:
        code, report = EXIT_REFUSED, {"refused": str(exc)}
    except ValueError as exc:
        # A bad `--field` pair, and every `ids.IdError` — that family subclasses
        # ValueError, so a second handler for it would be unreachable.
        code, report = EXIT_REFUSED, {"refused": str(exc)}
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
