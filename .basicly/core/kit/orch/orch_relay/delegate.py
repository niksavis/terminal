from __future__ import annotations

import argparse
import json
import os
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import runner
from orch_lessons.log import RefusedError
from orch_state import store

from orch_relay import adapters, install, record

FOLDER = "delegations"
TIMEOUT = 1800
ANSWER_MAX = 6000
TAIL = 800
KEYS = ("vendor", "record", "repo", "lane", "session")
USAGE = (
    "orch delegate --vendor claude|codex|copilot --record RECORD --prompt TEXT [--model M], "
    "or orch delegate --resume SESSION --prompt TEXT"
)

Exec = Callable[[list[str], Path], runner.Done]
Scan = Callable[[str], str | None]


def run_step(argv: list[str], cwd: Path) -> runner.Done:
    return runner.attempt(argv, TIMEOUT, str(cwd))


def add_parser(groups: argparse._SubParsersAction) -> None:
    given = groups.add_parser(
        "delegate", usage=USAGE, help="hand one turn to another coding agent in a lane"
    )
    given.add_argument("--vendor")
    given.add_argument("--record")
    given.add_argument("--resume", metavar="SESSION")
    given.add_argument("--model")
    given.add_argument("--prompt", required=True)


@dataclass(frozen=True)
class Delegation:
    vendor: str
    record: str
    repo: Path
    lane: str
    session: str


@dataclass(frozen=True)
class Ports:
    tracker: Callable[[Path], record.Tracker]
    scan: Callable[[Path], Scan]
    execute: Exec = run_step


def _path(base: Path, session: str) -> Path:
    return base / FOLDER / f"{store.SAFE.sub('_', session)[:80]}.json"


def _save(base: Path, found: Delegation) -> None:
    path = _path(base, found.session)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {key: str(getattr(found, key)) for key in KEYS}
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(value, out, sort_keys=True)
    Path(name).replace(path)


def _load(base: Path, session: str) -> Delegation:
    value = store.read(_path(base, session))
    if not all(isinstance(value.get(key), str) for key in KEYS):
        raise RefusedError(
            f"orch delegate --resume {session}: no delegation with that session is recorded "
            f"in {base / FOLDER}; start one with: {USAGE.split(', or ', maxsplit=1)[0]}"
        )
    vendor, record_id, repo, lane, found = (str(value[key]) for key in KEYS)
    return Delegation(vendor, record_id, Path(repo), lane, found)


def lane_name(record_id: str, vendor: str) -> str:
    return f"delegate-{record_id.replace('.', '-')}-{vendor}"


def _new(args: argparse.Namespace, repo: Path) -> Delegation:
    if not args.vendor or not args.record:
        raise RefusedError(f"orch delegate needs --vendor and --record, or --resume; run: {USAGE}")
    vendor = adapters.adapter(args.vendor)
    if not install.RECORD.fullmatch(args.record):
        raise RefusedError(f"--record {args.record!r} is not a record id; run: {USAGE}")
    session = str(uuid.uuid4()) if vendor.names_session else ""
    return Delegation(args.vendor, args.record, repo, lane_name(args.record, args.vendor), session)


def _lane(found: Delegation, execute: Exec) -> Path:
    path = adapters.lane_path(found.repo, found.lane)
    if path.exists():
        return path
    done = execute(["basicly", "worktree", "create", found.lane], found.repo)
    if done.code != 0 or not path.exists():
        raise RefusedError(
            f"orch delegate: basicly worktree create {found.lane} failed (exit {done.code}) in "
            f"{found.repo}; nothing was sent to {found.vendor}\n{(done.err or done.out)[-TAIL:]}"
        )
    return path


def _comment(found: Delegation, answer: str, scan: Scan, resume: bool) -> str:
    turn = "resumed turn" if resume else "answer"
    if hit := scan(answer):
        body = f"withheld: the secret scanner rule {hit} matched; read it in the agent session"
    else:
        body = answer if len(answer) <= ANSWER_MAX else answer[:ANSWER_MAX] + " [cut]"
    return f"[delegate {found.vendor} {turn}, session {found.session}, lane {found.lane}] {body}"


def _turn(args: argparse.Namespace, base: Path, repo: Path) -> tuple[Delegation, bool]:
    if args.resume and (args.vendor or args.record):
        raise RefusedError(
            f"orch delegate --resume takes the coding agent and record it recorded; run: {USAGE}"
        )
    if args.resume:
        return _load(base, args.resume), True
    return _new(args, repo), False


def run(args: argparse.Namespace, repo: Path, base: Path, ports: Ports) -> list[str]:
    found, resume = _turn(args, base, repo)
    vendor = adapters.adapter(found.vendor)
    tracker, scan = ports.tracker(found.repo), ports.scan(found.repo)
    lane = _lane(found, ports.execute)
    turn = adapters.Turn(args.prompt, found.session or None, resume, args.model)
    done = ports.execute(vendor.argv(turn), lane)
    if limited := adapters.usage_limit(found.vendor, done):
        raise limited
    if done.code != 0:
        kept = f"resume it with: {vendor.resume_command(found.session)}" if found.session else ""
        raise RefusedError(
            f"orch delegate: {found.vendor} exited {done.code} in {lane}; {kept}\n"
            f"{(done.err or done.out)[-TAIL:]}"
        )
    reply = vendor.reply(done, turn)
    found = replace(found, session=reply.session)
    _save(base, found)
    tracker.comment(found.record, _comment(found, reply.text, scan, resume))
    return [
        f"delegate: {found.vendor} session {found.session} in lane {found.lane} ({lane})",
        f"comment: written on {found.record}",
        f"answer: {reply.text}",
        f"next turn: orch delegate --resume {found.session} --prompt TEXT",
        f"agent resume: cd {lane} && {vendor.resume_command(found.session)}",
    ]
