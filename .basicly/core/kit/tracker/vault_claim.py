from __future__ import annotations

import importlib.util
import math
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_claim.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
events = _load("events.py", "basicly_tracker_kit_events")
vault_clone = _load("vault_clone.py", "basicly_tracker_kit_vault_clone")
vault_queue = _load("vault_queue.py", "basicly_tracker_kit_vault_queue")
vault_share = _load("vault_share.py", "basicly_tracker_kit_vault_share")
vault_fold = _load("vault_fold.py", "basicly_tracker_kit_vault_fold")

DEADLINE = 30.0
PROBE = 5.0
FRESH = 1.0
JOIN_WAIT = 0.05
STALL = 5.0
POLL = 0.1
TAKEOVER_FLOOR = 1.35
TAKEOVER_MARGIN = 1.5
TAKEOVER_NAME = "takeover.s"
LANDED = 0
FIX = 1
NAME_SESSION = (
    "name the session with --session, or set BASICLY_TRACKER_SESSION; "
    "a Claude Code or orch session uses its own session id"
)
LOST = 3
UNSETTLED = 4
UNREACHABLE = 5
INTERNAL = 6
YOURS = 7

Clock = Callable[[], float]
_INTERNAL = (
    OSError,
    LookupError,
    TypeError,
    ValueError,
    AttributeError,
    RuntimeError,
    git_runner.GitRunnerError,
    events.LedgerError,
)
Runner = Callable[..., str]


@dataclass(frozen=True)
class Ask:
    clone: Any
    state: Path
    record: str
    session: str
    clock: Callable[[], float]
    runner: Callable[..., str] = git_runner.run
    name: str = ""


NAME_MAX = 100
NAME_FIX = "set your holder name first: `git config basicly.holder 'your name'`, then claim again"
NAME_UNSAFE = (
    "the holder name from git config basicly.holder looks like a path, a secret or control text; "
    "set a plain name: `git config basicly.holder 'your name'`"
)


def name_refusal(name: str) -> str:

    if not name:
        return NAME_FIX
    if len(name) > NAME_MAX or not name.isprintable() or vault_queue.redact.text(name) != name:
        return NAME_UNSAFE
    return ""


class _Budget:
    def __init__(self, deadline: float, ticks: Clock) -> None:
        self._end = ticks() + deadline - min(POLL, deadline / 2)
        self._ticks = ticks
        self.timing: dict[str, float] = {}
        self.refresh_failed = False

    def add(self, key: str, seconds: object) -> None:
        value = float(seconds) if isinstance(seconds, (int, float)) else 0.0
        self.timing[key] = round(self.timing.get(key, 0.0) + value, 3)

    def now(self) -> float:
        return self._ticks()

    def left(self, cap: float | None = None) -> float:
        remaining = max(0.0, self._end - self._ticks())
        return remaining if cap is None else min(cap, remaining)


def _state(clone: Any, record: str) -> Any:
    return vault_fold.fold(vault_clone.valid_events(clone)).records.get(record)


def holder(clone: Any, record: str) -> tuple | None:
    state = _state(clone, record)
    return None if state is None else state.holder


def _held_elsewhere(record: str, vault: str, held: tuple, name: str = "") -> dict[str, object]:
    return {
        "exit": LOST,
        "record": record,
        "holder": {"writer": held[0], "session": held[1], "name": name},
        "next": f"unassign {record} --take --vault {vault}",
    }


def _released_here(clone: Any, record: str) -> bool:
    queued = vault_queue.pending(clone.folder / vault_queue.QUEUE_NAME)
    return any(
        line.get("kind") == vault_fold.UNASSIGN and line.get("record") == record for line in queued
    )


def _lost(clone: Any, record: str) -> dict[str, object] | None:
    state = _state(clone, record)
    if state is None or state.holder is None:
        return None
    return _held_elsewhere(record, clone.url, state.holder, state.name)


def _unsettled(record: str, vault: str, why: str) -> dict[str, object]:
    return {
        "exit": UNSETTLED,
        "record": record,
        "unsettled": why,
        "next": [
            f"claim {record} --wait --vault {vault}",
            f"claim {record} --cancel --vault {vault}",
        ],
    }


def _check(ask: Ask, budget: _Budget, writer: str) -> dict[str, object] | None:

    clone = ask.clone
    vault_clone.private(clone.folder)
    check = f"git fetch {clone.url} refs/heads/main"
    try:
        fetched = vault_clone.fetch_with(
            clone,
            vault_clone.Fetch(
                clock=ask.clock,
                runner=ask.runner,
                timeout=min(PROBE, budget.left() / 2),
                lock_wait=budget.left(),
                coalesce=True,
            ),
        )
    except (
        vault_clone.CloneError,
        git_runner.GitTimeoutError,
    ):
        fetched = {"fetched": False}
    budget.add("fetch_lock_wait_s", fetched.get("fetch_lock_wait_s"))
    if not fetched.get("fetched"):
        return {"exit": UNREACHABLE, "record": ask.record, "check": check}
    held = holder(clone, ask.record)
    if held == (writer, ask.session):
        mine = {"writer": writer, "session": ask.session, "name": ask.name}
        return {"exit": YOURS, "record": ask.record, "holder": mine}
    if held is None or _released_here(clone, ask.record):
        return None
    return _lost(clone, ask.record)


def _recorded_takeover(folder: Path) -> float:
    try:
        seconds = float(vault_clone._read(folder / TAKEOVER_NAME).strip() or "0")
    except OSError, ValueError:
        return 0.0
    return seconds if math.isfinite(seconds) and seconds > 0 else 0.0


def takeover_reserve(folder: Path) -> float:
    return max(TAKEOVER_FLOOR, TAKEOVER_MARGIN * _recorded_takeover(folder))


def _record_takeover(folder: Path, seconds: float, *, took_over: bool) -> None:
    if took_over and seconds > _recorded_takeover(folder):
        vault_clone.durable(folder / TAKEOVER_NAME, f"{seconds:.3f}\n")


def _stalled(joined_at: float | None, left: float, reserve: float) -> bool:
    if joined_at is None:
        return False
    return joined_at - left >= min(STALL, joined_at / 2) or left <= reserve


def _decided(ask: Ask, made: str, writer: str) -> bool:
    try:
        with events.LedgerLock(ask.clone.folder / "fetch", timeout_s=0):
            if made in vault_clone.valid_ids(ask.clone):
                return True
            held = holder(ask.clone, ask.record)
    except events.LockUnavailableError:
        return False
    if held is None or held == (writer, ask.session):
        return False
    return not _released_here(ask.clone, ask.record)


def _share_or_join(ask: Ask, budget: _Budget, made: str, fresh: bool) -> bool:

    joined_at = None
    reserve = takeover_reserve(ask.clone.folder)
    writer = vault_queue.writer_of(ask.state)
    progress = vault_clone._read(ask.clone.folder / vault_share.PROGRESS_NAME)

    def decided() -> bool:
        return _decided(ask, made, writer)

    while True:
        if decided():
            return joined_at is not None
        if budget.left() <= 0:
            raise vault_share.DeadlineError("the claim deadline expired")
        latest = vault_clone._read(ask.clone.folder / vault_share.PROGRESS_NAME)
        if joined_at is not None and latest and latest != progress:
            joined_at = budget.left()
        progress = latest
        stalled = _stalled(joined_at, budget.left(), reserve)
        plan = vault_share.Plan(
            ask.clock,
            urgent=True,
            deadline_s=budget.left(),
            fresh=fresh and joined_at is None,
            lock_wait=min(JOIN_WAIT, budget.left()),
            keep_going=False,
            unlocked=stalled,
            stop_when=decided,
        )
        asked = budget.now()
        try:
            shared = vault_share.share(
                ask.clone, ask.state, plan=plan, runner=ask.runner, clock=budget.now
            )
        except (
            vault_share.DeadlineError,
            git_runner.GitTimeoutError,
        ):
            if decided():
                return joined_at is not None
            raise
        except events.LockUnavailableError:
            budget.add("joined_wait_s", budget.now() - asked)
            joined_at = budget.left() if joined_at is None else joined_at
            if made in vault_clone.valid_ids(ask.clone):
                return True
            if budget.left() <= POLL:
                raise
            if _wait_join(ask, budget, decided):
                return True
            continue
        _record_takeover(ask.clone.folder, budget.now() - asked, took_over=stalled)
        budget.add("share_lock_wait_s", shared.get("lock_wait_s"))
        budget.add("fetch_lock_wait_s", shared.get("fetch_lock_wait_s"))
        if decided() or shared.get("ended"):
            return joined_at is not None
        fresh = False


def _wait_join(ask: Ask, budget: _Budget, decided: Callable[[], bool]) -> bool:
    if _refresh_join(ask, budget) or decided():
        return True
    if budget.left() > POLL:
        time.sleep(POLL)
        budget.add("joined_wait_s", POLL)
    return False


def _refresh_join(ask: Ask, budget: _Budget) -> bool:
    if budget.refresh_failed:
        return False
    stamp = vault_clone._read(ask.clone.folder / vault_clone.FETCHED_NAME).strip()
    if stamp and ask.clock() - float(stamp) < POLL:
        return False
    allowance = min(PROBE * 2, budget.left() / 2)
    end = budget.now() + allowance
    fetch_failed = False

    def runner(args: list[str], cwd: Path, **options: Any) -> str:
        nonlocal fetch_failed
        left = end - budget.now()
        if left <= 0:
            raise git_runner.GitTimeoutError("the helper refresh allowance expired")
        options["timeout"] = min(float(options.get("timeout", left)), left)
        try:
            result = ask.runner(args, cwd, **options)
        except git_runner.GitRunnerError:
            if args[0] == "fetch":
                fetch_failed = True
            raise
        if args[0] == "fetch":
            fetch_failed = False
        return result

    request = vault_clone.Fetch(
        clock=ask.clock,
        runner=runner,
        timeout=allowance / 2,
        lock_wait=0,
        coalesce=True,
    )
    try:
        shown = vault_clone.fetch_with(ask.clone, request)
    except events.LockUnavailableError:
        return False
    except vault_clone.CloneError, git_runner.GitTimeoutError:
        budget.refresh_failed = fetch_failed
        return False
    budget.refresh_failed = not shown.get("fetched", False)
    budget.add("fetch_lock_wait_s", shown.get("fetch_lock_wait_s"))
    if shown.get("retracted") or vault_clone.unrepaired(ask.clone, ask.runner, budget.left()):
        raise vault_share.ShareError("the vault dropped seen commits; run fsck --repair --vault")
    return vault_clone.ended(ask.clone) is not None


def _land(ask: Ask, budget: _Budget, writer: str, fetched_left: float) -> dict[str, object]:

    clone, record = ask.clone, ask.record
    origin = vault_queue.Origin(ask.session, False, ask.clock)
    draft = {"kind": "claim", "record": record, "payload": {vault_fold.HOLDER_NAME: ask.name}}
    made = vault_queue.write(clone, [draft], state=ask.state, origin=origin)["events"][0]
    fresh = fetched_left - budget.left() < FRESH
    try:
        joined = _share_or_join(ask, budget, made, fresh)
    except (
        vault_share.DeadlineError,
        git_runner.GitTimeoutError,
        events.LockUnavailableError,
    ) as exc:
        return {**_unsettled(record, clone.url, str(exc)), "claim": made}
    held = holder(clone, record)
    if held == (writer, ask.session):
        return {"exit": LANDED, "record": record, "claim": made, "joined": joined}
    if held is None:
        return {**_unsettled(record, clone.url, "the claim has not landed yet"), "claim": made}
    if _released_here(clone, record):
        why = f"this clone's release of {record} is not shared yet"
        return {
            **_unsettled(record, clone.url, why),
            "claim": made,
            "next": [vault_queue.share_command(clone.url)],
        }
    return _lost(clone, record) or _held_elsewhere(record, clone.url, held)


def _attempt(ask: Ask, budget: _Budget) -> dict[str, object]:
    started = budget.now()

    def runner(args: list[str], cwd: Path, **options: Any) -> str:
        left = budget.left()
        if left <= 0:
            raise git_runner.GitTimeoutError("the claim deadline expired")
        options["timeout"] = min(float(options.get("timeout", left)), left)
        return ask.runner(args, cwd, **options)

    bounded = replace(ask, runner=runner)
    writer = vault_queue.writer_of(ask.state)
    early = _check(bounded, budget, writer)
    shown = early if early is not None else _land(bounded, budget, writer, budget.left())
    budget.add("claim_s", budget.now() - started)
    return {**shown, "timing": dict(budget.timing)}


def claim(
    ask: Ask, *, ticks: Clock = time.monotonic, deadline: float = DEADLINE
) -> dict[str, object]:

    clone, record, session, clock = ask.clone, ask.record, ask.session, ask.clock
    if not session:
        return {"exit": FIX, "fix": NAME_SESSION}
    if not record or not record.isprintable() or record.startswith("-"):
        return {
            "exit": FIX,
            "fix": "name the record id to claim, as in claim acme-a1b2 --vault ...",
        }
    if refused := name_refusal(ask.name):
        return {"exit": FIX, "record": record, "fix": refused}
    try:
        return _attempt(ask, _Budget(deadline, ticks))
    except vault_share.ShareError as exc:
        return {"exit": FIX, "record": record, "fix": str(exc)}
    except _INTERNAL:
        log = clone.folder / "log" / f"claim-{int(clock())}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
        return {
            "exit": INTERNAL,
            "record": record,
            "log": str(log),
            "next": vault_queue.share_command(clone.url),
        }
