from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Callable
from pathlib import Path

import runner
from orch_lessons import log
from orch_lessons.log import RefusedError
from orch_relay import record
from orch_state import store

from orch_pace import costs, plan, snapshot

Clock = Callable[[], int]
MOMENTS = ("start", "done")
VAULT_CONFIG = ".basicly-tracker.toml"
QUICK_S = 15
SETUP = (
    "wrap the status line command in ~/.claude/settings.json as "
    "'orch-statusline-tap -- <your command>' (docs/design/usage-snapshot.md)"
)
START_MARK = "[pace start]"
DONE_MARK = "[pace done]"
START_NOTE = re.compile(
    r"^\[pace start\] five_hour=(?P<used>[0-9.]+) resets_at=(?P<resets>[0-9]+)(?: |$)"
)


def add_parsers(groups: argparse._SubParsersAction) -> None:
    pace = groups.add_parser("pace")
    actions = pace.add_subparsers(dest="action")
    note = actions.add_parser("note")
    note.add_argument("record")
    note.add_argument("moment", choices=MOMENTS)
    note.set_defaults(by="manual")


def now_s() -> int:
    return int(time.time())


def _state(path: Path, document: object, now: int) -> str:
    if not isinstance(document, dict) or document.get("format") != snapshot.FORMAT:
        return "unreadable or not " + snapshot.FORMAT
    if document.get("version") != snapshot.VERSION:
        version = document.get("version")
        return f"version {version!r}; this orch reads version {snapshot.VERSION}"
    if not snapshot.written_by(document, path.stem):
        return f"writer field is not {path.stem!r}"
    five = snapshot.windows(document).get("five_hour")
    if five is None:
        return "no five_hour reading"
    age = now - int(five["read_at"])  # type: ignore[call-overload]
    if age > plan.STALE_S:
        return f"stale: last five_hour reading {plan.span(age)} old"
    return ""


def fresh(environ: dict[str, str], now: int) -> tuple[Path, list[str], dict[str, snapshot.Window]]:
    where = snapshot.folder(environ)
    found = snapshot.documents(where)
    if not found:
        raise RefusedError(f"no usage snapshot in {where}; {SETUP}")
    kept: list[tuple[str, dict[str, snapshot.Window]]] = []
    skipped: list[str] = []
    for path, document in found:
        why = _state(path, document, now)
        if why:
            skipped.append(f"{path.name}: {why}")
        else:
            kept.append((path.stem, snapshot.windows(document)))
    if not kept:
        raise RefusedError(
            f"no fresh usage snapshot in {where} ({'; '.join(skipped)}); a five_hour reading "
            f"must be under {plan.STALE_S // 60} minutes old; a status line refresh writes one"
        )
    combined: dict[str, snapshot.Window] = {}
    for name in snapshot.WINDOWS:
        chosen = snapshot.best([w[name] for _, w in kept if name in w])
        if chosen is not None:
            combined[name] = chosen
    return where, [writer for writer, _ in kept], combined


def show(
    environ: dict[str, str], now: int, cwd: Path, tracker: record.Tracker | None = None
) -> str:
    where, writers, windows = fresh(environ, now)
    paces = [plan.pace(name, windows[name], now) for name in snapshot.WINDOWS if name in windows]
    lines = [f"usage snapshots in {where}, fresh from: {', '.join(writers)}"]
    lines += [plan.line(p, now) for p in paces]
    lines.append(f"advice: {plan.overall(paces)}")
    if "five_hour" in windows:
        lines.append(plan.fit_line(windows["five_hour"], now, working_count(cwd, environ)))
    lines += costs.lines(cwd, tracker)
    return "\n".join(lines)


def _dead(session: dict[str, object]) -> bool:
    pid, began = session.get("pid"), session.get("pid_start")
    return isinstance(pid, int) and isinstance(began, int) and store.alive(pid, began) is False


def working_count(cwd: Path, environ: dict[str, str]) -> int:
    root = store.find(cwd, environ)
    if root is None:
        return 0
    return sum(1 for s in store.sessions(root) if s.get("state") == "working" and not _dead(s))


def working(cwd: Path, environ: dict[str, str]) -> str:
    if store.find(cwd, environ) is None:
        return ""
    return f" working_sessions={working_count(cwd, environ)}"


def note(
    args: argparse.Namespace,
    cwd: Path,
    environ: dict[str, str],
    now: int,
    tracker: record.Tracker | None = None,
) -> str:
    by = getattr(args, "by", "manual")
    _, _, windows = fresh(environ, now)
    five = windows["five_hour"]
    used, resets = float(five["used_percentage"]), int(five["resets_at"])  # type: ignore[arg-type, call-overload]
    found = tracker or record.Tracker(log.repo_root(cwd))
    head = f"five_hour={used:.1f} resets_at={resets}"
    if args.moment == "start":
        text = f"{START_MARK} {head}{working(cwd, environ)} by={by}"
        found.comment(args.record, text)
        return f"noted on {args.record}: {text}"
    shown = json.loads(found.runner([*found.base, "show", found.ledger, args.record]))
    notes = shown.get("comment_log", []) if isinstance(shown, dict) else []
    starts = [
        m
        for n in notes
        if isinstance(n, dict) and isinstance(n.get("text"), str)
        for m in [START_NOTE.match(n["text"])]
        if m is not None
    ]
    if not starts:
        raise RefusedError(
            f"{args.record} has no {START_MARK} note; run: orch pace note {args.record} start"
        )
    began = starts[-1]
    fields = shown.get("fields", {}) if isinstance(shown, dict) else {}
    kind = fields.get("issue_type", "") if isinstance(fields, dict) else ""
    same = abs(resets - int(began["resets"])) <= snapshot.CYCLE_APART_S
    change = f"{used - float(began['used']):.1f}" if same else "unknown_crossed_reset"
    kind = kind or "unknown"
    text = f"{DONE_MARK} {head} change={change} type={kind}{working(cwd, environ)} by={by}"
    found.comment(args.record, text)
    return f"noted on {args.record}: {text}"


def quick(argv: list[str]) -> str:
    done = runner.attempt(argv, QUICK_S)
    if done.code != 0:
        raise RefusedError(f"the tracker refused: {done.err.strip() or done.out.strip()}")
    return done.out


def auto(cwd: Path, environ: dict[str, str], args: argparse.Namespace) -> bool:
    try:
        repo = log.repo_root(cwd)
        if not (repo / VAULT_CONFIG).is_file():
            return False
        note(args, cwd, environ, now_s(), record.Tracker(repo, quick))
    except RefusedError, OSError, ValueError, KeyError, TypeError:
        return False
    return True


def run(
    args: argparse.Namespace, cwd: Path, environ: dict[str, str], clock: Clock = now_s
) -> str | None:
    if args.group != "pace":
        return None
    if args.action == "note":
        return note(args, cwd, environ, clock())
    return show(environ, clock(), cwd)
