from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from orch_relay import classes, messages, record, start

from orch_lessons import doctor, log


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="orch")
    groups = top.add_subparsers(dest="group", required=True)
    lesson = groups.add_parser("lesson").add_subparsers(dest="action", required=True)
    add = lesson.add_parser("add")
    add.add_argument("--what", required=True)
    add.add_argument("--requirement", required=True)
    add.add_argument("--enforcement", required=True)
    add.add_argument("--record", required=True)
    close = lesson.add_parser("close")
    close.add_argument("id")
    close.add_argument("--change", required=True)
    many = groups.add_parser("lessons").add_subparsers(dest="action", required=True)
    init = many.add_parser("init")
    init.add_argument("folder", type=Path)
    export = many.add_parser("export")
    export.add_argument("--target", type=Path, required=True)
    export.add_argument("--out", required=True)
    many.add_parser("end-session")
    groups.add_parser("doctor")
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
    groups.choices["approve"].add_argument("--words", required=True)
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
    return top


def relay(args: argparse.Namespace, writer: messages.Writer) -> str:
    act = messages.Action(
        args.item,
        args.record or record.find(writer.tracker),
        args.repo,
        args.action,
        args.risk,
    )
    if args.group == "approve":
        return writer.approve(act, args.words)
    why = messages.Decision(
        args.rule,
        args.rule_date,
        args.reason,
        args.condition,
        args.proof,
        args.if_proof_fails,
    )
    return writer.decide(act, why)


def run_relay(args: argparse.Namespace, cwd: Path) -> int | None:
    if args.group == "send":
        print(messages.order(args.to, args.record, args.goal, args.limits, args.proof))
        return 0
    if args.group == "start":
        repo = log.repo_root(cwd)
        print(shlex.join(start.launch(args.vendor, args.role, args.name, repo)))
        return 0
    if args.group not in ("record", "decide", "approve", "report"):
        return None
    repo = log.repo_root(cwd)
    tracker = record.Tracker(repo)
    if args.group == "record":
        print(record.find(tracker))
        return 0
    writer = messages.Writer(tracker, log.scanner(repo))
    if args.group == "report":
        print(writer.report(args.record, args.state, args.summary, args.recommend))
        return 0
    print(relay(args, writer))
    return 0


def _add(args: argparse.Namespace, writer: log.Writer) -> str:
    return f"lesson {writer.add(args.what, args.requirement, args.enforcement, args.record)} added"


def _close(args: argparse.Namespace, writer: log.Writer) -> str:
    writer.close(args.id, args.change)
    return f"lesson {args.id} closed"


def _end_session(_args: argparse.Namespace, writer: log.Writer) -> str:
    return f"session ended with {writer.end_session()} lesson(s)"


WRITES = {
    ("lesson", "add"): _add,
    ("lesson", "close"): _close,
    ("lessons", "end-session"): _end_session,
}


def run(argv: list[str], cwd: Path, environ: dict[str, str]) -> int:
    args = parser().parse_args(argv)
    if args.group == "lessons" and args.action == "init":
        print(f"lessons folder ready: {log.init(args.folder)}")
        return 0
    relayed = run_relay(args, cwd)
    if relayed is not None:
        return relayed
    if args.group == "doctor":
        report = doctor.run(cwd, environ)
        print("\n".join(report.lines))
        return 1 if report.failed else 0
    root = log.find_root(cwd, environ)
    scan = log.scanner(log.repo_root(cwd))
    if (args.group, args.action) in WRITES:
        print(WRITES[args.group, args.action](args, log.Writer(root, scan, log.member(environ))))
        return 0
    repo = log.repo_root(cwd)
    target = args.target.resolve()
    patch = log.export(root, scan, target, target.relative_to(repo).as_posix())
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
