from __future__ import annotations

import argparse
from typing import Any

DEFAULT_STATUS = "open"

DIRECTORY_HELP = "the ledger directory"


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


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, read, query and advance work items in a tracker kit ledger."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="mint a record id and append its first events")
    create.add_argument("directory", help=DIRECTORY_HELP)
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
    show.add_argument("directory", help=DIRECTORY_HELP)
    show.add_argument("record", help="the record id")

    listing = sub.add_parser("list", help="query the records the ledger holds")
    listing.add_argument("directory", help=DIRECTORY_HELP)
    listing.add_argument("--status", default=None, help="only records at this status")
    listing.add_argument("--limit", type=int, default=None, help="at most this many records")

    compaction = sub.add_parser(
        "compact", help="fold every pending writer shard into the trunk log and unlink it"
    )
    compaction.add_argument("directory", help=DIRECTORY_HELP)
    compaction.add_argument(
        "--writer",
        action="append",
        default=[],
        metavar="WRITER",
        help="only this writer's shard; repeats. Every shard when omitted",
    )

    shards = sub.add_parser("shards", help="the pending writer shards this ledger holds")
    shards.add_argument("directory", help=DIRECTORY_HELP)

    page = sub.add_parser("board", help="write one self-contained HTML page a human can open")
    page.add_argument("directory", help=DIRECTORY_HELP)
    page.add_argument("--out", default="tracker-board.html", help="the file to write")

    check = sub.add_parser(
        "fsck", help="fold the whole log and report anything unparseable or broken"
    )
    check.add_argument("directory", help=DIRECTORY_HELP)
    check.add_argument(
        "--rebuild",
        action="store_true",
        help="delete every derived file and write it again from the log before checking",
    )

    gate = sub.add_parser(
        "dor",
        help="the definition of ready: refuse a record that cannot be verified against",
    )
    gate.add_argument("directory", help=DIRECTORY_HELP)
    gate.add_argument("record", help="the record id")

    bring = sub.add_parser(
        "import", help="import a foreign tracker's JSONL export into this ledger"
    )
    bring.add_argument("directory", help=DIRECTORY_HELP)
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

    shape = sub.add_parser("scaffold", help="print what a record of one type must carry")
    shape.add_argument("directory", help=DIRECTORY_HELP)
    shape.add_argument("--type", default="", help="the record type, as its issue_type field")

    _add_query_parsers(sub)
    _add_write_parsers(sub)
    return parser


def _add_query_parsers(sub: Any) -> None:
    for name, helping in (
        ("ready", "the ranked ready set: what can be worked on now"),
        ("blocked", "each dispatchable record that is not ready, and what holds it"),
        ("stats", "counts by status, plus the ready and blocked counts"),
        ("fields", "each record field, its role and its reader"),
        ("refine", "the open records a refinement pass owes: labelled refine or not ready"),
        ("migrate-fields", "move section-only acceptance criteria and requirements into fields"),
    ):
        view = sub.add_parser(name, help=helping)
        view.add_argument("directory", help=DIRECTORY_HELP)
        if name == "ready":
            view.add_argument("--limit", type=int, default=None, help="at most this many")
            view.add_argument("--mine", action="store_true", help="only records you hold")


def _add_write_parsers(sub: Any) -> None:
    child = sub.add_parser("child", help="mint the next child id under a parent")
    child.add_argument("directory", help=DIRECTORY_HELP)
    child.add_argument("parent", help="the parent record id")
    child.add_argument("--title", default="", help="the record's title")
    child.add_argument("--field", action="append", default=[], metavar="NAME=VALUE")
    child.add_argument("--status", default=DEFAULT_STATUS, help="the status to open it at")
    _add_shape_arguments(child)

    update = sub.add_parser("update", help="set a record's fields, status or labels")
    update.add_argument("directory", help=DIRECTORY_HELP)
    update.add_argument("record", help="the record id")
    update.add_argument("--field", action="append", default=[], metavar="NAME=VALUE")
    update.add_argument("--status", default="", help="the status to move it to")
    update.add_argument("--add-label", action="append", default=[], metavar="LABEL")
    update.add_argument("--remove-label", action="append", default=[], metavar="LABEL")
    _add_shape_arguments(update)

    closing = sub.add_parser("close", help="move records to the closed status")
    closing.add_argument("directory", help=DIRECTORY_HELP)
    closing.add_argument("record", nargs="+", help="the record ids to close")
    closing.add_argument("--reason", default="", help="why, recorded as a field")

    note = sub.add_parser("comment", help="append one comment to a record")
    note.add_argument("directory", help=DIRECTORY_HELP)
    note.add_argument("record", help="the record id")
    note.add_argument("text", help="the comment body")

    dep = sub.add_parser("dep", help="record a dependency edge on the dependent")
    dep.add_argument("directory", help=DIRECTORY_HELP)
    dep.add_argument("record", help="the dependent record id")
    dep.add_argument("target", help="the record it depends on")
    dep.add_argument("--type", dest="edge_type", default="blocks", help="the edge type")

    for name, helping in (
        ("assign", "reserve a record for a person without changing its status"),
        ("claim", "reserve a record for a person and set it in_progress"),
    ):
        hold = sub.add_parser(name, help=helping)
        hold.add_argument("directory", help=DIRECTORY_HELP)
        hold.add_argument("record", help="the record id")
        hold.add_argument("--to", default="", help="the holder; default: git config user.name")
        hold.add_argument("--take", action="store_true", help="take it from its current holder")

    settle = sub.add_parser("resolve", help="keep the current value of each conflicting fork")
    settle.add_argument("directory", help=DIRECTORY_HELP)
    settle.add_argument("record", help="the record id")

    release = sub.add_parser("unassign", help="give a reserved record back")
    release.add_argument("directory", help=DIRECTORY_HELP)
    release.add_argument("record", help="the record id")

    removal = sub.add_parser("delete", help="tombstone a record; its id is never reused")
    removal.add_argument("directory", help=DIRECTORY_HELP)
    removal.add_argument("record", help="the record id")
