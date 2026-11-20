from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from orch_lessons.log import RefusedError

from orch_state import relay_guard, status, store

SESSION_ENVS = ("ORCH_SESSION_ID", "CLAUDE_CODE_SESSION_ID")
NAME_ENV = "ORCH_MEMBER"
RELAY_TEXT = {
    "report": "report {state} {record}",
    "decide": "decided {item} {record}",
    "approve": "relayed approval {record}",
}
NO_STORE = (
    "no orchestrator store found above {cwd}; run: "
    "orch lessons init <workspace>/.orchestrator/lessons, or set " + store.ROOT_ENV
)


def add_parsers(groups: argparse._SubParsersAction) -> None:
    state = groups.add_parser("state").add_subparsers(dest="action", required=True)
    put = state.add_parser("set")
    for flag in ("--now", "--next", "--waiting", "--name", "--session"):
        put.add_argument(flag)
    put.add_argument("--state", choices=store.STATES)
    groups.add_parser("status")
    ask = groups.add_parser("ask")
    ask.add_argument("--record")
    ask.add_argument("--question")
    ask.add_argument("--options")
    ask.add_argument("--withdraw", metavar="RECORD")


def base(cwd: Path, environ: dict[str, str]) -> Path:
    found = store.find(cwd, environ)
    if found is None:
        raise RefusedError(NO_STORE.format(cwd=cwd))
    return found


def session(environ: dict[str, str], given: str | None) -> str:
    chosen = given or next((environ[k] for k in SESSION_ENVS if environ.get(k)), "")
    if not chosen.strip():
        raise RefusedError(
            "orch state set needs the session id: pass --session ID, or set ORCH_SESSION_ID"
        )
    return chosen.strip()


def process_fields(start: int) -> dict[str, object]:
    found = store.vendor_process(start)
    if found is None:
        return {}
    pid, began, vendor = found
    return {"pid": pid, "pid_start": began, "vendor": vendor}


def _name(args: argparse.Namespace, environ: dict[str, str], current: object) -> str | None:
    name = store.clean(args.name or environ.get(NAME_ENV, ""), 40) or None
    if relay_guard.reserved(name) or (name and relay_guard.reserved(current)):
        raise RefusedError(
            f"orch state set cannot give or change the name {relay_guard.ORCHESTRATOR}; "
            "only the session started with that name gets it, from its SessionStart hook"
        )
    return name


def set_state(
    args: argparse.Namespace, cwd: Path, environ: dict[str, str], clock: store.Clock
) -> str:
    root, chosen = base(cwd, environ), session(environ, args.session)
    current = store.read(store.session_path(root, chosen)).get("name")
    changes: dict[str, object] = {
        "name": _name(args, environ, current),
        "project": store.project(cwd),
        "next": store.clean(args.next) if args.next is not None else None,
        "waiting_on": store.clean(args.waiting) if args.waiting is not None else None,
        "state": args.state,
        **process_fields(os.getppid()),
    }
    if args.now is not None:
        changes["now"] = store.clean(args.now)
        changes["now_at"] = store.stamp(clock)
    if args.state is not None:
        changes["state_at"] = store.stamp(clock)
    record = store.save(root, chosen, changes, clock)
    return f"state saved for {record.get('name') or record['id']}"


def run_ask(args: argparse.Namespace, root: Path, clock: store.Clock) -> str:
    if args.withdraw:
        if not store.close_ask(root, args.withdraw, "withdrawn", clock):
            raise RefusedError(f"no open ask for {args.withdraw}; list them with: orch status")
        return f"ask for {args.withdraw} withdrawn"
    if not args.record or not args.question or not args.question.strip():
        raise RefusedError(
            "orch ask needs --record R --question TEXT [--options A|B], or --withdraw R"
        )
    store.ask(root, args.record, args.question, args.options, clock)
    return f"ask for {args.record} opened"


def run(
    args: argparse.Namespace, cwd: Path, environ: dict[str, str], clock: store.Clock = store.utc_now
) -> str | None:
    if args.group == "state":
        return set_state(args, cwd, environ, clock)
    if args.group == "status":
        root = base(cwd, environ)
        columns = shutil.get_terminal_size((status.WIDTH, 24)).columns
        lines = status.render(store.sessions(root), store.asks(root), clock(), store.alive, columns)
        return "\n".join(lines) if lines else "no session has written its state yet"
    if args.group == "ask":
        return run_ask(args, base(cwd, environ), clock)
    return None


def after_relay(
    args: argparse.Namespace, cwd: Path, environ: dict[str, str], clock: store.Clock = store.utc_now
) -> None:
    root = store.find(cwd, environ)
    chosen = next((environ[k] for k in SESSION_ENVS if environ.get(k)), "")
    if root is None:
        return
    if args.group == "approve" and args.record:
        store.close_ask(root, args.record, "approved", clock)
    if not chosen:
        return
    texts = {
        "report": lambda: (
            f"report {args.state} {args.record}",
            "orchestrator" if args.state != "done" else None,
        ),
        "decide": lambda: (f"decided {args.item} {args.record or ''}", None),
        "approve": lambda: (f"relayed approval {args.record or ''}", None),
    }
    if args.group not in texts:
        return
    text, waiting = texts[args.group]()
    changes: dict[str, object] = {
        "now": store.clean(text),
        "now_at": store.stamp(clock),
        "project": store.project(cwd),
    }
    if waiting:
        changes["waiting_on"] = waiting
    store.save(root, chosen, changes, clock)
