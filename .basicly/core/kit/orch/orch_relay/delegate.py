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

from orch_relay import adapters, console, failures, install, record, tiers

FOLDER = "delegations"
TIMEOUT = 1800
ANSWER_MAX = 6000
TAIL = 800
KEYS = ("vendor", "record", "repo", "lane", "session")
READ_ONLY = "read-only"
USAGE = (
    "orch delegate --vendor claude|codex|copilot --record RECORD --prompt TEXT "
    "[--read-only] [--model M | --tier T] [--billing subscription|console], "
    "or orch delegate --resume SESSION --prompt TEXT"
)

Exec = Callable[[list[str], Path, dict[str, str] | None], runner.Done]
Scan = Callable[[str], str | None]


def run_step(argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> runner.Done:
    return runner.attempt(argv, TIMEOUT, str(cwd), env)


def add_parser(groups: argparse._SubParsersAction) -> None:
    given = groups.add_parser(
        "delegate", usage=USAGE, help="hand one turn to another coding agent in a lane"
    )
    given.add_argument("--vendor")
    given.add_argument("--record")
    given.add_argument("--resume", metavar="SESSION")
    given.add_argument("--model")
    given.add_argument("--tier")
    given.add_argument("--read-only", action="store_true")
    given.add_argument("--billing", choices=console.BILLINGS)
    given.add_argument("--prompt", required=True)


@dataclass(frozen=True)
class Delegation:
    vendor: str
    record: str
    repo: Path
    lane: str
    session: str
    read_only: bool = False
    billing: str = "subscription"
    tier: str = ""


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
    value["mode"] = READ_ONLY if found.read_only else "lane"
    value["billing"], value["tier"] = found.billing, found.tier
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
    billing, tier = str(value.get("billing", "subscription")), str(value.get("tier", ""))
    read_only = value.get("mode") == READ_ONLY
    return Delegation(vendor, record_id, Path(repo), lane, found, read_only, billing, tier)


def lane_name(record_id: str, vendor: str) -> str:
    return f"delegate-{record_id.replace('.', '-')}-{vendor}"


def _new(args: argparse.Namespace, repo: Path) -> Delegation:
    if not args.vendor or not args.record:
        raise RefusedError(f"orch delegate needs --vendor and --record, or --resume; run: {USAGE}")
    vendor = adapters.adapter(args.vendor)
    if not install.RECORD.fullmatch(args.record):
        raise RefusedError(f"--record {args.record!r} is not a record id; run: {USAGE}")
    billing = args.billing or "subscription"
    if billing == "console" and args.vendor != "claude":
        raise RefusedError(
            f"orch delegate --billing console runs only claude, not {args.vendor!r}; run: {USAGE}"
        )
    session = str(uuid.uuid4()) if vendor.names_session else ""
    lane = "" if args.read_only else lane_name(args.record, args.vendor)
    return Delegation(args.vendor, args.record, repo, lane, session, args.read_only, billing)


def _lane(found: Delegation, execute: Exec) -> Path:
    path = adapters.lane_path(found.repo, found.lane)
    if path.exists():
        return path
    done = execute(["basicly", "worktree", "create", found.lane], found.repo, None)
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
    where = READ_ONLY if found.read_only else f"lane {found.lane}"
    return f"[delegate {found.vendor} {turn}, session {found.session}, {where}] {body}"


def _turn(args: argparse.Namespace, base: Path, repo: Path) -> tuple[Delegation, bool]:
    if args.resume and (args.vendor or args.record or args.read_only or args.billing):
        raise RefusedError(
            f"orch delegate --resume takes the coding agent, record and mode it recorded; "
            f"run: {USAGE}"
        )
    if args.tier and args.model:
        raise RefusedError(f"orch delegate takes --tier or --model, not both; run: {USAGE}")
    if args.resume:
        return _load(base, args.resume), True
    return _new(args, repo), False


def _model(args: argparse.Namespace, base: Path, vendor: str) -> str | None:
    return tiers.model(base, args.tier, vendor) if args.tier else args.model


def _plan(args: argparse.Namespace, base: Path, found: Delegation) -> console.Plan | None:
    if found.billing != "console":
        return None
    tier = found.tier or args.tier
    chosen = console.plan(base, tier, None if tier else args.model, found.read_only)
    console.refuse_budget(base, chosen)
    return chosen


def _refuse_read_only_resume(found: Delegation, vendor: adapters.Adapter) -> None:
    if found.read_only and not getattr(vendor, "resumes_read_only", False):
        raise RefusedError(
            f"orch delegate --resume {found.session}: {found.vendor} cannot resume a read-only "
            f"session read-only; start a new one with --read-only"
        )


def _next(found: Delegation, vendor: adapters.Adapter) -> str:
    if found.read_only and not getattr(vendor, "resumes_read_only", False):
        return f"next turn: {found.vendor} resumes no read-only session; start a new one"
    return f"next turn: orch delegate --resume {found.session} --prompt TEXT"


def run(args: argparse.Namespace, repo: Path, base: Path, ports: Ports) -> list[str]:
    found, resume = _turn(args, base, repo)
    vendor = adapters.adapter(found.vendor)
    if resume:
        _refuse_read_only_resume(found, vendor)
    plan = _plan(args, base, found)
    model = plan.model if plan else _model(args, base, found.vendor)
    found = replace(found, tier=plan.tier) if plan else found
    tracker, scan = ports.tracker(found.repo), ports.scan(found.repo)
    lane = found.repo if found.read_only else _lane(found, ports.execute)
    if plan:
        console.refuse_place(plan, lane)
    turn = adapters.Turn(
        args.prompt,
        found.session or None,
        resume,
        model,
        found.read_only,
        None if found.read_only else str(lane),
    )
    argv = console.argv(plan, vendor.argv(turn)) if plan else vendor.argv(turn)
    adapters.refuse_bypass(found.vendor, argv)
    held = console.reserve(base, plan, found.record, found.session) if plan else None
    done = ports.execute(argv, lane, console.env(plan) if plan else None)
    spend = console.settle(base, held, done) if held else None
    limited = adapters.usage_limit(found.vendor, done)
    saved = failures.save(base, found.vendor, argv, args.prompt, done) if done.code else None
    if limited:
        raise adapters.UsageLimitError(
            f"{limited}; the failure is saved in {saved}" if saved else str(limited)
        )
    if saved:
        kept = f"resume it with: {vendor.resume_command(found.session)}" if found.session else ""
        raise RefusedError(
            f"orch delegate: {found.vendor} exited {done.code} in {lane}; {kept}; "
            f"the failure is saved in {saved}\n{(done.err or done.out)[-TAIL:]}"
        )
    reply = vendor.reply(done, turn)
    found = replace(found, session=reply.session)
    _save(base, found)
    tracker.comment(found.record, _comment(found, reply.text, scan, resume))
    where = f"read-only in {lane}" if found.read_only else f"in lane {found.lane} ({lane})"
    return [
        f"delegate: {found.vendor} session {found.session} {where}",
        f"comment: written on {found.record}",
        f"answer: {reply.text}",
        _next(found, vendor),
        f"agent resume: cd {lane} && {vendor.resume_command(found.session)}",
        f"rules: {' '.join(adapters.rules(argv)) or 'none'}",
        *([spend] if spend else []),
    ]
