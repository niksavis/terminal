from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections.abc import Callable, Sequence
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


_load("bootstrap.py", "basicly_tracker_bootstrap").require_runtime()
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
cli_fields = _load("cli_fields.py", "basicly_tracker_kit_cli_fields")
vault_migration_cli = _load("vault_migration_cli.py", "basicly_tracker_kit_vault_migration_cli")
arguments = _load("arguments.py", "basicly_tracker_kit_arguments")
vault_arguments = _load("vault_arguments.py", "basicly_tracker_kit_vault_arguments")
vault_config = _load("vault_config.py", "basicly_tracker_kit_vault_config")
vault_cli = _load("vault_cli.py", "basicly_tracker_kit_vault_cli")
vault_refusal = _load("vault_refusal.py", "basicly_tracker_kit_vault_refusal")
pin = _load("pin.py", "basicly_tracker_kit_pin")
mirror = _load("mirror.py", "basicly_tracker_kit_mirror")
settings = _load("settings.py", "basicly_tracker_kit_settings")
beans = _load("beans.py", "basicly_tracker_kit_beans")
refine_sheet = _load("refine_sheet.py", "basicly_tracker_kit_refine_sheet")
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
    "undep",
    "delete",
    "dor",
})

_STARTS_A_LEDGER = frozenset({"create", "import"})


_field_value = cli_fields.field_value
_fields = cli_fields.fields
_shape_fields = cli_fields.shape_fields


def _minting(fields: dict[str, object]) -> dict[str, object]:
    fields.setdefault(shaping.SHAPED_UNDER_FIELD, shaping.SHAPING_RULE)
    return fields


create_record = commands.create_root
query_records = queries.query_records
read_record = record_view.read_record
_owed_of = record_view.owed_of


_WRITES: dict[str, Callable[[argparse.Namespace, Any], Sequence[Any]]] = {
    "child": lambda a, c: commands.create_child(
        a.directory,
        a.parent,
        _minting(_fields(a.title, a.field, a)),
        status=a.status,
        context=c,
    ),
    "update": lambda a, c: commands.update(
        a.directory,
        a.record,
        fields=_fields("", a.field, a),
        status=a.status,
        add_labels=a.add_label,
        remove_labels=a.remove_label,
        context=c,
        if_seq=a.if_seq,
        claimant=_holder(a),
    ),
    "close": lambda a, c: commands.close(
        a.directory, a.record, reason=a.reason, resolution=a.resolution, context=c
    ),
    "review": lambda a, c: commands.record_process(
        a.directory, a.record, json.loads(a.evidence), redact=c
    ),
    "confirm": lambda a, c: commands.record_process(
        a.directory, a.record, json.loads(a.evidence), completed=True, redact=c
    ),
    "comment": lambda a, c: commands.comment(a.directory, a.record, a.text, context=c),
    "dep": lambda a, c: commands.add_dependency(
        a.directory, a.record, a.target, edge_type=a.edge_type, context=c
    ),
    "undep": lambda a, c: commands.remove_dependency(
        a.directory, a.record, a.target, edge_type=a.edge_type, context=c
    ),
    "delete": lambda a, c: commands.delete(a.directory, a.record, context=c),
    "assign": lambda a, c: commands.assign(
        a.directory, a.record, _holder(a), take=a.take, context=c
    ),
    "claim": lambda a, c: commands.claim(a.directory, a.record, _holder(a), take=a.take, context=c),
    "unassign": lambda a, c: commands.unassign(
        a.directory, a.record, _holder(a, "by"), take=a.take, context=c
    ),
    "mark-ready": lambda a, c: commands.mark_ready(
        a.directory, a.record, _holder(a), mode=a.mode, context=c
    ),
    "resolve": lambda a, c: commands.resolve(a.directory, a.record, context=c),
    "acknowledge-loss": lambda a, c: fsck.recovery.acknowledge(
        a.directory,
        a.record,
        fsck.recovery.Request(tuple(a.sequence), a.reason, tuple(a.evidence)),
        redact=c.redactor,
    ),
}


def _holder(args: argparse.Namespace, given: str = "to") -> str:
    return getattr(args, given, "") or commands.holders.default_holder(Path.cwd(), os.environ)


def _compacted(args: argparse.Namespace) -> dict[str, object]:
    done = snapshot.compact(args.directory, writers=tuple(args.writer))
    return {
        "trunk": done.trunk.name,
        "shards": [path.name for path in done.shards],
        "appended": done.appended,
        "duplicates": done.duplicates,
    }


_VIEWS: dict[str, Callable[[argparse.Namespace, Any], dict[str, object]]] = {
    "ready": lambda a, _r: queries.ready(
        a.directory, limit=a.limit, mine=_holder(a) if a.mine else ""
    ),
    "blocked": lambda a, _r: queries.blocked(a.directory),
    "stats": lambda a, _r: queries.stats(a.directory),
    "compact": lambda a, _r: _compacted(a),
    "shards": lambda a, _r: fsck.shards_report(a.directory),
    "board": lambda a, _r: {"written": board.write(a.directory, a.out).as_posix()},
    "import": lambda a, c: beans.import_backlog(
        a.directory,
        beans.Source(a.source_format, Path(a.export), a.source or None),
        redact=c.redactor,
        dry_run=a.dry_run,
    ),
    "refine-sheet": lambda a, _r: refine_sheet.write(
        a.directory, refine_sheet.sheet_path(a.directory, a.out)
    ),
    "apply-sheet": lambda a, c: refine_sheet.apply(
        a.directory,
        refine_sheet.sheet_path(a.directory, a.sheet),
        context=c,
        view=lambda: vault_cli.view_of(a, c.clock),
    ),
    "sync": lambda a, _r: mirror.sync(a.directory, a.root, dry_run=a.dry_run),
    "scaffold": lambda a, _r: record_view.scaffold_of(a.directory, a.type),
    "fields": lambda a, _r: fields.table(record_view.templates.load(a.directory)),
    "refine": lambda a, _r: record_view.refine_queue(a.directory),
    "migrate-fields": lambda a, c: {
        "appended": [event.record for event in commands.migrate_fields(a.directory, context=c)]
    },
    "config": lambda a, _r: (
        settings.write(a.directory, a.name, a.value)
        if a.config_action == "set"
        else settings.report(a.directory, start=Path.cwd())
    ),
}


def _shown(args: argparse.Namespace, clock: Callable[[], float]) -> tuple[int, Any]:
    if getattr(args, "json", False):
        shown = vault_cli.shown(args.directory, [args.record], clock)
        return (EXIT_OK if all(one.get("found", True) for one in shown) else EXIT_REFUSED), shown
    found = record_view.read_view(
        args.directory, args.record, view=args.view, snapshot=args.snapshot
    )
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


def _relative(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _commit_check(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    message = Path(args.message).read_text(encoding="utf-8")
    changed = [line.strip() for line in sys.stdin] if args.stdin else list(args.path)
    linked = [
        path.name
        for pattern in ("events-*.jsonl", "pending-*.jsonl")
        for path in Path(args.directory).glob(pattern)
        if path.is_symlink()
    ]
    if linked:
        raise commands.claims.UnclaimedError(
            f"the staged ledger contains symlink files {', '.join(sorted(linked))}; "
            "stage regular event files before committing"
        )
    found, unreadable = events.read_events(args.directory)
    states = events.fold(found).records
    committer = commands.holders.default_holder(Path.cwd(), os.environ)
    ledger = Path(args.directory).resolve()
    runner = args.runner or commands.holders.kit_cli()
    shown = args.ledger_label or _relative(ledger)
    context = commands.claims.CommitContext(committer, shown, runner, tuple(args.installed))
    if unreadable:
        raise commands.claims.UnclaimedError(
            f"the staged ledger {shown} has unreadable events; run `{runner} fsck {shown}` "
            "and repair the ledger before committing"
        )
    commands.claims.refuse_commit(states, message, changed, context)
    return EXIT_OK, {"committer": committer, "ids": commands.claims.named_ids(message, states)}


_REFUSABLE: dict[str, Callable[[argparse.Namespace, Callable[[], float]], tuple[int, Any]]] = {
    "commit-check": lambda a, _c: _commit_check(a),
    "show": _shown,
    "dor": lambda a, _c: _dor(a),
    "fsck": lambda a, _c: _fsck(a),
}


def _migration(
    args: argparse.Namespace, redact: Callable[[str], str] | None, clock: Callable[[], float]
) -> dict[str, object]:
    state = None if args.preview or args.state else vault_cli._state_root()
    return vault_migration_cli.run(args, redact, clock, state)


def _run(args: argparse.Namespace, redact: Callable[[str], str] | None) -> tuple[int, Any]:
    clock = events.wall_clock(getattr(args, "clock", None))
    if args.command == "bootstrap":
        return _load("bootstrap.py", "basicly_tracker_bootstrap").run(args.repository, clock)
    return _run_command(args, redact, clock)


def _run_command(
    args: argparse.Namespace, redact: Callable[[str], str] | None, clock: Callable[[], float]
) -> tuple[int, Any]:
    if not (args.command == "migrate" and getattr(args, "freeze", False)):
        vault_cli.check_frozen()
    context = commands.vault_write.WriteContext(redact, clock)
    vault_cli.route_ledger_alias(args)
    vault = vault_cli.HANDLERS.get(args.command)
    if args.command == "migrate" or vault is not None:
        report = (
            _migration(args, redact, clock)
            if args.command == "migrate"
            else vault(args, context if args.command == "comment-vault" else clock)
        )
        code = report.pop("exit", EXIT_OK)
        code = code if isinstance(code, int) else EXIT_OK
        if code != EXIT_OK and not isinstance(report.get("refused"), str):
            report["refused"] = commands.vault_write.redact.text(
                vault_refusal.message(code, report)
            )
        return code, report
    vault_refusal.refuse_ledger_form(args, commands, vault_config)
    setting = args.command == "config" and getattr(args, "config_action", "") == "set"
    starts = (args.command in _STARTS_A_LEDGER or setting) and not getattr(args, "dry_run", False)
    args.directory = commands.resolve_ledger(args.directory, starts=starts)
    pin.require(args.directory)
    if args.command in vault_cli.READS and not (
        args.command == "show" and getattr(args, "json", False)
    ):
        args.directory = vault_cli.view_of(args, clock)
    if args.command == "create":
        written = create_record(
            args.directory,
            _minting(_fields(args.title, args.field, args)),
            prefix=settings.create_prefix(args.directory, args.prefix),
            status=args.status,
            context=context,
        )
        record = written[0].record
        return EXIT_OK, {
            "record": record,
            "events": [event.id for event in written],
            **_owed_of(vault_cli.view_of(args, clock), record),
        }
    if (gate := _REFUSABLE.get(args.command)) is not None:
        return gate(args, clock)
    if (view := _VIEWS.get(args.command)) is not None:
        return EXIT_OK, view(args, context)
    if (write := _WRITES.get(args.command)) is not None:
        appended = write(args, context)
        if appended:
            record = appended[0].record
        else:
            ids = args.record
            record = ids if isinstance(ids, str) else ids[0]
        return EXIT_OK, {
            "record": record,
            "events": [event.id for event in appended],
            "appended": bool(appended),
            **commands.parent_progress.started(appended, record),
            **_owed_of(vault_cli.view_of(args, clock), record),
        }
    records = queries.listed(args)
    return EXIT_OK, {"count": len(records), "records": records}


def invoke(args: argparse.Namespace, redact: Callable[[str], str] | None = None) -> tuple:

    report: Any
    try:
        code, report = _run(args, redact)
    except commands.vault_write.VaultRefusedError as exc:
        report = dict(exc.report)
        code = report.pop("exit", EXIT_REFUSED)
        code = code if isinstance(code, int) else EXIT_REFUSED
        report["refused"] = commands.vault_write.redact.text(vault_refusal.message(code, report))
    except (events.FrozenLedgerError, vault_cli.ledger_freeze.FreezeError) as exc:
        code, report = 2, {"refused": str(exc)}
    except events.LedgerError as exc:
        code, report = EXIT_REFUSED, {"refused": str(exc)}
    except ValueError as exc:
        code, report = EXIT_REFUSED, {"refused": str(exc)}
    if isinstance(report, list):
        return code, report
    version = 2 if args.command in _BLOCKING_REPORTS else 1
    return code, {"schema": f"{SCHEMA_PREFIX}.{args.command}.v{version}", **report}


def command_names() -> list[str]:
    parser = arguments.parser(refine_sheet.add_parsers)
    return sorted(next(one.choices for one in parser._actions if isinstance(one.choices, dict)))


def main(argv: Sequence[str] | None = None, *, redact: Callable[[str], str] | None = None) -> int:

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["bootstrap"]:
        return int(_load("bootstrap.py", "basicly_tracker_bootstrap").main(argv[1:]))
    argv = list(vault_config.with_vault(argv, Path.cwd(), vault_arguments.routed_verbs(argv)))
    verb = argv[0] if argv else ""
    routed = "--vault" in argv or verb in vault_arguments.VAULT_ONLY
    form = vault_arguments.FORMS.get(verb) if routed else None
    parser = form() if form else arguments.parser(refine_sheet.add_parsers)
    args = parser.parse_args(argv)
    with commands.vault_write.given_session(os.environ, getattr(args, "session", None)):
        code, report = invoke(args, redact)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
