from __future__ import annotations

import argparse
import importlib.metadata
import shlex
import sys
from pathlib import Path

from orch_automode import commands as automode
from orch_pace import commands as pace
from orch_relay import accept, brief, classes, delegate, install, messages, record, start
from orch_state import commands, relay_guard, store

from orch_lessons import doctor, log


def version() -> str:
    try:
        return f"orch {importlib.metadata.version('basicly-orch')}"
    except importlib.metadata.PackageNotFoundError:
        return "orch from a kit folder, not an installed package"


def _top() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="orch")
    top.add_argument("--version", action="version", version=version())
    return top


def parser() -> argparse.ArgumentParser:
    top = _top()
    groups = top.add_subparsers(dest="group", required=True)
    _lesson_parsers(groups)
    install.add_parser(groups)
    delegate.add_parser(groups)
    groups.add_parser("doctor")
    _relay_parsers(groups)
    commands.add_parsers(groups)
    pace.add_parsers(groups)
    automode.add_parsers(groups)
    return top


def _lesson_parsers(groups: argparse._SubParsersAction) -> None:
    lesson = groups.add_parser("lesson").add_subparsers(dest="action", required=True)
    add = lesson.add_parser("add")
    add.add_argument("--what", required=True)
    add.add_argument("--requirement", required=True)
    add.add_argument("--enforcement", required=True)
    add.add_argument("--record", required=True)
    add.add_argument("--scope")
    close = lesson.add_parser("close")
    close.add_argument("id")
    close.add_argument("--change", required=True)
    rescope = lesson.add_parser("scope")
    rescope.add_argument("id")
    rescope.add_argument("value")
    many = groups.add_parser("lessons").add_subparsers(dest="action", required=True)
    init = many.add_parser("init")
    init.add_argument("folder", type=Path)
    export = many.add_parser("export")
    export.add_argument("--target", type=Path, required=True)
    export.add_argument("--out", required=True)
    many.add_parser("end-session")


def _relay_parsers(groups: argparse._SubParsersAction) -> None:
    groups.add_parser("record")
    for name in ("decide", "approve"):
        relay = groups.add_parser(name)
        relay.add_argument("--item", choices=sorted(classes.ITEMS), required=True)
        relay.add_argument("--record")
        relay.add_argument("--repo", required=True)
        relay.add_argument("--action", required=True)
        relay.add_argument("--risk", action="append", default=[])
    decide = groups.choices["decide"]
    for flag in ("--rule", "--rule-date", "--reason", "--condition", "--proof", "--if-proof-fails"):
        decide.add_argument(flag, required=True)
    decide.add_argument("--council", default="")
    groups.choices["approve"].add_argument("--words", required=True)
    groups.choices["approve"].add_argument("--diff", action="store_true")
    send = groups.add_parser("send")
    send.add_argument("--order", action="store_true", required=True)
    send.add_argument("--to", required=True)
    send.add_argument("--record", required=True)
    for flag in ("--goal", "--limits", "--proof"):
        send.add_argument(flag, default="")
    report = groups.add_parser("report")
    report.add_argument("--record", required=True)
    report.add_argument("--state", required=True)
    report.add_argument("--summary", required=True)
    report.add_argument("--recommend")
    launch = groups.add_parser("start")
    launch.add_argument("--vendor", choices=start.VENDORS, required=True)
    launch.add_argument("--name", required=True)
    launch.add_argument("--role", default="orchestrator")


def relay(args: argparse.Namespace, writer: messages.Writer) -> str:
    act = messages.Action(
        args.item,
        args.record or record.find(writer.tracker),
        args.repo,
        args.action,
        args.risk,
    )
    if args.group == "approve":
        return writer.approve(act, args.words, args.diff)
    why = messages.Decision(
        args.rule,
        args.rule_date,
        args.reason,
        args.condition,
        args.proof,
        args.if_proof_fails,
        args.council,
    )
    return writer.decide(act, why)


def _read(args: argparse.Namespace, cwd: Path, environ: dict[str, str]) -> str | None:
    if args.group == "accept":
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
        return accept.check(text, args.record, args.repo, args.action)
    if args.group == "brief":
        tracker = record.Tracker(log.repo_root(cwd))
        found = record.find(tracker)
        shown = brief.notes(tracker.notes(found))
        return brief.render(found, shown, commands.session_lines(cwd, environ))
    return None


def run_install(args: argparse.Namespace, cwd: Path, environ: dict[str, str]) -> int:
    found = store.find(cwd, environ)
    if found is None:
        raise log.RefusedError(commands.NO_STORE.format(cwd=cwd))
    for line in install.run(found.parent, args.release, args.repo, args.dry_run):
        print(line, flush=True)
    return 0


def run_send(args: argparse.Namespace, _cwd: Path, _environ: dict[str, str]) -> int:
    print(messages.order(args.to, args.record, args.goal, args.limits, args.proof))
    return 0


def run_delegate(args: argparse.Namespace, cwd: Path, environ: dict[str, str]) -> int:
    if args.list:
        print("\n".join(delegate.listing(args)))
        return 0
    found = store.find(cwd, environ)
    if found is None:
        raise log.RefusedError(commands.NO_STORE.format(cwd=cwd))
    ports = delegate.Ports(record.Tracker, log.scanner)
    try:
        lines = delegate.run(args, log.repo_root(cwd), found, ports)
    except delegate.adapters.UsageLimitError as limited:
        print(f"orch: {limited}", file=sys.stderr)
        return 3
    print("\n".join(lines))
    return 0


DIRECT = {"install": run_install, "send": run_send, "delegate": run_delegate}


def run_relay(args: argparse.Namespace, cwd: Path, environ: dict[str, str]) -> int | None:
    if (direct := DIRECT.get(args.group)) is not None:
        return direct(args, cwd, environ)
    if (shown := _read(args, cwd, environ)) is not None:
        print(shown)
        return 0
    if args.group == "start":
        repo = log.repo_root(cwd)
        print(shlex.join(start.launch(args.vendor, args.role, args.name, repo)))
        return 0
    if args.group not in ("record", "decide", "approve", "report"):
        return None
    session = (
        relay_guard.check(args.group, cwd, environ) if args.group in ("decide", "approve") else ""
    )
    repo = log.repo_root(cwd)
    tracker = record.Tracker(repo)
    if args.group == "record":
        print(record.find(tracker))
        return 0
    writer = messages.Writer(tracker, log.scanner(repo), session=session)
    if args.group == "report":
        print(writer.report(args.record, args.state, args.summary, args.recommend))
        print(messages.send_step(args.record))
    else:
        print(relay(args, writer))
    commands.after_relay(args, cwd, environ)
    return 0


def _add(args: argparse.Namespace, writer: log.Writer) -> str:
    lesson_id = writer.add(args.what, args.requirement, args.enforcement, args.record, args.scope)
    return f"lesson {lesson_id} added"


def _close(args: argparse.Namespace, writer: log.Writer) -> str:
    writer.close(args.id, args.change)
    return f"lesson {args.id} closed"


def _scope(args: argparse.Namespace, writer: log.Writer) -> str:
    writer.scope(args.id, args.value)
    return f"lesson {args.id} scoped {args.value}"


def _end_session(_args: argparse.Namespace, writer: log.Writer) -> str:
    return f"session ended with {writer.end_session()} lesson(s)"


WRITES = {
    ("lesson", "add"): _add,
    ("lesson", "close"): _close,
    ("lesson", "scope"): _scope,
    ("lessons", "end-session"): _end_session,
}


def run(argv: list[str], cwd: Path, environ: dict[str, str]) -> int:
    args = parser().parse_args(argv)
    if args.group == "lessons" and args.action == "init":
        print(f"lessons folder ready: {log.init(args.folder)}")
        return 0
    relayed = run_relay(args, cwd, environ)
    if relayed is not None:
        return relayed
    shown = commands.run(args, cwd, environ)
    if shown is None:
        shown = pace.run(args, cwd, environ)
    if shown is None:
        shown = automode.run(args, cwd, environ)
    if shown is not None:
        print(shown)
        return 0
    if args.group == "doctor":
        report = doctor.run(cwd, environ)
        print("\n".join(report.lines))
        return 1 if report.failed else 0
    root = log.find_root(cwd, environ)
    scan = log.scanner(log.repo_root(cwd))
    if (args.group, args.action) in WRITES:
        print(
            WRITES[args.group, args.action](
                args, log.Writer(root, scan, commands.member_name(cwd, environ))
            )
        )
        return 0
    repo = log.repo_root(cwd)
    target = args.target.resolve()
    patch = log.export(root, scan, target, target.relative_to(repo).as_posix())
    if missing := log.unscoped(root):
        print(
            f"{len(missing)} open lesson(s) have no scope and were left out: {', '.join(missing)}; "
            "scope each with: orch lesson scope ID local|basicly",
            file=sys.stderr,
        )
    if args.out == "-":
        sys.stdout.write(patch)
    else:
        Path(args.out).write_text(patch, encoding="utf-8")
        print(f"patch written: {args.out}")
    return 0


def main() -> int:
    try:
        return run(sys.argv[1:], Path.cwd(), log.environ())
    except log.RefusedError as refusal:
        print(f"orch: {refusal}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
